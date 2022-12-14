""" 
Author: Jonathan Zhang <jon.zhang@ucsf.edu>

This file contains classes for modelling the kinetics of chemical reaction networks.
"""

#imports
import re
import numpy as np
from scipy.integrate import odeint
from collections import OrderedDict

class ChemicalReactionNetwork:
    """
    Class for an arbitrary network of chemical reactions.

    Attributes
    ----------
    species: list
        A list of all chemical species present.
    mass_action_reactions: list
        A list of MassActionReactions objects, each describing a
        reaction modelled by mass action kinetics.
    michaelis_menten_reactions: list
        A list of MichaelisMentenReactions objectseach 
        describing a reaction modelled by MM kinetics.
    time: np.ndarray
        An array of times to solve over.
    initial_concentrations: np.ndarray  
        Defines the initial state of the chemical system.
    update_dictionary: dict
        A dictionary of functions for updating reaction rates or 
        initial concentrations. 
    concentrations: np.ndarray
        Array of concentrations of each specie at each timepoint.
    """

    def __init__(self, mass_action_dict: dict, michaelis_menten_dict: dict, initial_concentrations: dict, time: np.ndarray):
        characters = {'*', '->', '+', '<->'}
        self.species = list(set([specie for specie in sum([i.split(' ') for i in {**mass_action_dict, **michaelis_menten_dict}.keys()], []) if specie not in characters and not specie.isnumeric()])) #parses through chemical equation strings to find all unique species
        self.mass_action_reactions = ChemicalReactionNetwork._parse_mass_action(ChemicalReactionNetwork._process_reaction_dict(mass_action_dict), self.species)
        self.michaelis_menten_reactions = ChemicalReactionNetwork._parse_michaelis_menten(michaelis_menten_dict, self.species)
        self.time = time
        self.initial_concentrations = np.array([initial_concentrations[specie] if specie in initial_concentrations.keys() else 1e-50 for specie in self.species]) #generates initial values based on initial_concentrations
        self.update_dictionary = self._create_update_dictionary()
        self.concentrations = None #create a placeholder for concentrations attribute

    @staticmethod
    def _process_reaction_dict(reaction_dict: dict):
        """
        Splits reversible reactions into elementary reactions.
        """

        updated_reaction_dict = {}
        for reaction in reaction_dict.keys():
            if '<->' in reaction:
                forward_constant, reverse_constant = reaction_dict[reaction].keys()
                split = reaction.split(' ')
                split[split.index('<->')] = '->'
                _forward, _reverse = split, split
                forward, reverse = ' '.join(_forward), ' '.join(_reverse[::-1])
                updated_reaction_dict[forward] = OrderedDict({forward_constant: reaction_dict[reaction][forward_constant]})
                updated_reaction_dict[reverse] = OrderedDict({reverse_constant: reaction_dict[reaction][reverse_constant]})
            else:
                updated_reaction_dict[reaction] = reaction_dict[reaction]
        return updated_reaction_dict

    @staticmethod
    def _parse_mass_action(mass_action_dict: dict, species: list):
        """
        Static method for processing dictionaries with reactions to
        be modeled with mass action kinetics.
        """

        #if no mass action reactions, instantiate a dummy
        if len(mass_action_dict) == 0:
            return MassActionReactions()

        A, N, rate_names, rates = [], [], [], []
        reactions = list(mass_action_dict.keys())
        for reaction in reactions:
            rate_name, rate = list(mass_action_dict[reaction].items())[0]
            rate_names.append(rate_name), rates.append(rate)
            b, a = np.zeros(len(species)), np.zeros(len(species))

            #split chemical equation into products and substrates
            _substrates, _products = reaction.split('->')
            _substrates, _products = [re.sub(re.compile(r'\s+'), '', sub).split('*') for sub in _substrates.split('+')], [re.sub(re.compile(r'\s+'), '', prod).split('*') for prod in _products.split('+')]
            for _substrate in _substrates:
                #get substrate stoichiometries and names
                substrate = _substrate[1] if len(_substrate) == 2 else _substrate[0]
                stoichiometry_coeff = int(_substrate[0]) if len(_substrate) == 2 else 1
                a[species.index(substrate)] = stoichiometry_coeff
            for _product in _products:
                #get product stoichiometries and names
                if _product == ['0']:
                    continue
                product = _product[1] if len(_product) == 2 else _product[0]
                stoichiometry_coeff = int(_product[0]) if len(_product) == 2 else 1
                b[species.index(product)] = stoichiometry_coeff
            A.append(a)
            N.append(b-a)
        return MassActionReactions(reactions, A, N, rate_names, rates)

    @staticmethod
    def _parse_michaelis_menten(michaelis_menten_dict: dict, species: list):
        """
        Static method for processing dictionaries with reactions to
        be modeled with MM kinetics.
        """

        #if no MM reactions, instantiate a dummy
        if len(michaelis_menten_dict) == 0:
            return MichaelisMentenReactions()
        
        substrates, enzymes, products, Kms, kcats = [], [], [], [], []
        reactions, rates = michaelis_menten_dict.keys(), michaelis_menten_dict.values()
        for reaction, rate in zip(reactions, rates):
            Km_key, kcat_key = [key for key in rate.keys() if 'Km' in key][0], [key for key in rate.keys() if 'kcat' in key][0]

            #split reaction equation into substrates and products
            _left, _right = reaction.split('->')
            left, right = [re.sub(re.compile(r'\s+'), '', sub).split('*') for sub in _left.split('+')], [re.sub(re.compile(r'\s+'), '', prod).split('*') for prod in _right.split('+')]
            left_species, left_stoichios, right_species, right_stoichios = [], [], [], []
            for specie in left:
                name = specie[1] if len(specie) == 2 else specie[0]
                left_species.append(name)
                stoichiometry_coeff = int(specie[0]) if len(specie) == 2 else 1
                left_stoichios.append(stoichiometry_coeff)
            for specie in right:
                name = specie[1] if len(specie) == 2 else specie[0]
                right_species.append(name)
                stoichiometry_coeff = int(specie[0]) if len(specie) == 2 else 1
                right_stoichios.append(stoichiometry_coeff)
                    
            enzyme = list(set(left_species).intersection(set(right_species)))[0] #enzyme is present on both sides of equation
            substrate = list(set(left_species) - set([enzyme]))[0] 
            product = list(set(right_species) - set([enzyme]))[0] 
            substrate_index, enzyme_index, product_index = species.index(substrate), species.index(enzyme), species.index(product)
            substrate_stoichiometry, product_stoichiometry = left_stoichios[left_species.index(substrate)], right_stoichios[right_species.index(product)]

            substrates.append((substrate_index, substrate_stoichiometry))
            products.append((product_index, product_stoichiometry))
            enzymes.append(enzyme_index)
            Kms.append((Km_key, rate[Km_key]))
            kcats.append((kcat_key, rate[kcat_key]))
        return MichaelisMentenReactions(list(reactions), substrates, enzymes, products, Kms, kcats)

    def _make_update_function(self, index: int, token: str):
        """ 
        Private method for defining functions to update rate constants
        and initial concentrations of chemical reaction network.
        """

        def update(new_value):
            if token == 'rate_constant':
                self.mass_action_reactions.K[index, index] = new_value
            elif token == 'Km':
                self.michaelis_menten_reactions.Kms[index] = new_value
            elif token == 'kcat':
                self.michaelis_menten_reactions.kcats[index] = new_value
            elif token == 'initial_concentration':
                self.initial_concentrations[index] = new_value
        return update

    def _create_update_dictionary(self):
        """ 
        Private method for creating update dictionary. Providing a species or 
        rate constant as a key name will yield a function for updating it.
        """

        mass_action_update, michaelis_menten_update, initial_concen_update = {}, {}, {}
        if self.mass_action_reactions.reactions:
            for rate_index, rate_name in enumerate(self.mass_action_reactions.rate_names):
                mass_action_update[rate_name] = self._make_update_function(rate_index, 'rate_constant')
        if self.michaelis_menten_reactions.reactions:
            for index, (Km_name, kcat_name) in enumerate(zip(self.michaelis_menten_reactions.Km_names, self.michaelis_menten_reactions.kcat_names)):
                michaelis_menten_update[Km_name], michaelis_menten_update[kcat_name] = self._make_update_function(index, 'Km'), self._make_update_function(index, 'kcat')
        for index, specie in enumerate(self.species):
            initial_concen_update[specie] = self._make_update_function(index, 'initial_concentration')
        return {**mass_action_update, **michaelis_menten_update, **initial_concen_update}

    def integrate(self, rtol=None, atol=None):
        """ 
        Method for numerical integration of ODE system associated 
        with the reaction network. Outputs nothing, but re-defines 
        the concentrations attribute.

        :param rtol, atol: hyperparameters that control the error tolerance
        of the numerical integrator.
        """

        #to make code as fast as possible, functions for computing mass action and MM rates are pre-defined, then called in ODEs
        if type(self.mass_action_reactions.reactions) == list:
            def compute_mass_action_rates(concentrations):
                return np.dot(self.mass_action_reactions.N.T, np.dot(self.mass_action_reactions.K, np.prod(np.power(concentrations, self.mass_action_reactions.A), axis=1)))
        elif self.mass_action_reactions.reactions == None:
            empty = np.zeros(len(self.species))
            def compute_mass_action_rates(concentrations):
                return empty
        if type(self.michaelis_menten_reactions.reactions) == list:
            def compute_michaelis_menten_rates(concentrations, michaelis_menten_reactions):
                return michaelis_menten_reactions.compute_velocities(concentrations)
        elif self.michaelis_menten_reactions.reactions == None:
            empty = np.zeros(len(self.species))
            def compute_michaelis_menten_rates(concentrations, michaelis_menten_reactions):
                return empty

        def ODEs(concentrations: np.ndarray, time: np.ndarray, michaelis_menten_reactions):
            return np.vstack((compute_michaelis_menten_rates(concentrations, michaelis_menten_reactions), compute_mass_action_rates(concentrations))).sum(axis=0)

        self.concentrations = odeint(ODEs, self.initial_concentrations, self.time, args=(self.michaelis_menten_reactions,), rtol=rtol, atol=atol).T

class MassActionReactions:
    """ 
    Class for reactions modelled with mass action kinetics.

    Attributes
    ----------
    reactions: list
        A list of chemical equations represented as strings.
    A: np.ndarray
        The substrate stoichiometry matrix for the mass action reactions.
    N: np.ndarray
        The reaction stoichiometry matrix for the mass action reactions.
    rate_names: list
        A list of rate names for each rate constant.
    K: np.ndarray
        The rate matrix for the mass action reactions.
    """

    def __init__(self, reactions=None, A=None, N=None, rate_names=None, rates=None):
        args =  [reactions, A, N, rate_names, rates]
        types = [type(arg) for arg in args]

        #if no arguments passed, instantiate a dummy
        if set(types) == set([type(None)]):
            self.reactions, self.N, self.A, self.rate_names, self.K = [None] * 5

        #otherwise, instantiate a bonafide object
        elif set(types) == set([list]):
            self.reactions = reactions
            self.N = np.vstack(N)
            self.A = np.vstack(A)
            self.rate_names = rate_names
            self.K = np.diag(np.array(rates))

        else:
            #set up handling of exceptions
            pass

class MichaelisMentenReactions:
    """ 
    Class for reactions modelled with MM kinetics.

    Attributes
    ----------
    reactions: list
        A list of chemical equations represented as strings.
    substrate_indices: np.ndarray 
        Indices of substrate species. Indexed by reaction.
    substrate_stoichiometries: np.ndarray
        Stoichiometries of substrates. Indexed by reaction.
    product_indices: np.ndarray 
        Indices of product species. Indexed by reaction.
    product_stoichiometries: np.ndarray 
        Stoichiometries of products. Indexed by reaction.
    enzyme_indices: np.ndarray
        Indices of enzyme species. Indexed by reaction.
    Km_names: np.ndarray
        Names of Km constants for each reaction.
    Kms: np.ndarray
        Values of Km constants for each reaction.
    kcat_names: np.ndarray
        Names of kcat constants for each reaction.
    kcats: np.ndarray
        Values of kcat constants for each reaction.
    """

    def __init__(self, reactions=None, substrates=None, enzymes=None, products=None, Kms=None, kcats=None):
        args = [reactions, substrates, enzymes, products, Kms, kcats]
        types = [type(arg) for arg in args]

        #if no arguments passed, instantiate a dummy
        if set(types) == set([type(None)]):
            self.reactions, self.substrate_indices, self.substrate_stoichiometries, self.product_indices, self.product_stoichiometries, \
            self.enzyme_indices, self.Km_names, self.Kms, self.kcat_names, self.kcats = [None] * 10

        #otherwise, instantiate a bonafide object
        elif set(types) == set([list]):
            self.reactions = reactions
            self.substrate_indices, self.substrate_stoichiometries = map(np.array,zip(*substrates))
            self.product_indices, self.product_stoichiometries = map(np.array,zip(*products))
            self.enzyme_indices = enzymes
            self.Km_names, self.Kms = map(np.array,zip(*Kms))
            self.kcat_names, self.kcats = map(np.array,zip(*kcats))

        else:
            #include something for error handling   
            pass
        
    def compute_velocities(self, concentrations: np.ndarray):
        """ 
        Function for vectorized calculation of MM rates using the
        quadratic MM equation (no free ligand approximation).
        """

        substrate_velocities, product_velocities = np.zeros(len(concentrations)), np.zeros(len(concentrations))
        substrate_vector = concentrations[self.substrate_indices]   
        enzyme_vector = concentrations[self.enzyme_indices] 

        term1 = np.vstack((substrate_vector, enzyme_vector, self.Kms)).sum(axis=0)
        t1, t2 = np.square(term1), np.vstack((enzyme_vector, substrate_vector)).prod(axis=0) * 4
        term2 = np.sqrt(np.subtract(t1, t2))
        _velocities = np.vstack((np.subtract(term1, term2), np.divide(self.kcats, 2))).prod(axis=0)

        substrate_velocities[self.substrate_indices] = np.vstack((_velocities, self.substrate_stoichiometries)).prod(axis=0) * -1
        product_velocities[self.product_indices] = np.vstack((_velocities, self.product_stoichiometries)).prod(axis=0)
        return np.vstack((substrate_velocities, product_velocities)).sum(axis=0)