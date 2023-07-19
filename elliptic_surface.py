# -*- coding: utf-8 -*-

from elliptic_singularity import EllipticSingularities
import sage.all

from numperiods import Family
from numperiods import IntegerRelations
from ore_algebra import *

from sage.modules.free_module_element import vector
from sage.rings.qqbar import QQbar
from sage.functions.other import factorial
from sage.matrix.constructor import matrix
from sage.rings.integer_ring import ZZ
from sage.matrix.special import identity_matrix
from sage.matrix.special import diagonal_matrix
from sage.matrix.special import block_matrix
from sage.matrix.special import block_diagonal_matrix
from sage.matrix.special import zero_matrix

from sage.rings.polynomial.polynomial_ring_constructor import PolynomialRing
from sage.rings.rational_field import QQ
from sage.schemes.toric.weierstrass import WeierstrassForm
from sage.misc.flatten import flatten

from sage.modules.free_quadratic_module_integer_symmetric import IntegralLattice

from voronoi import FundamentalGroupVoronoi
from integrator import Integrator
from Util import Util
from Context import Context
from periods import LefschetzFamily

import logging
import time

logger = logging.getLogger(__name__)


class EllipticSurface(object):
    def __init__(self, P,basepoint=None, **kwds):
        """P, a homogeneous polynomial defining an.

        This class aims at computing an effective basis of the homology group H_n(X), 
        given as lifts of paths through a Lefschetz fibration.
        """
        
        self.ctx = Context(**kwds)
        
        # assert P.is_homogeneous(), "nonhomogeneous defining polynomial"
        
        self._P = P
        self._family = Family(P)

        if basepoint!= None: # it is useful to be able to specify the basepoint to avoid being stuck in arithmetic computations if critical values have very large modulus
            self._basepoint=basepoint
        if not self.ctx.debug:
            fg = self.fundamental_group # this allows reordering the critical points straight away and prevents shenanigans. There should be a better way to do this
    
    
    @property
    def intersection_product(self):
        if not hasattr(self,'_intersection_product'):
            self._intersection_product=self._compute_intersection_product()
        return self._intersection_product

    @property
    def period_matrix(self):
        if not hasattr(self, '_period_matrix'):
            homology_mat = self.homology.transpose()
            integrated_thimbles =  matrix([self.integrated_thimbles])
            self._period_matrix = integrated_thimbles*homology_mat

        return self._period_matrix
    
    @property
    def periods_smoothing(self):
        if not hasattr(self, '_periods_smoothing'):
            homology_mat= self.homology*self.thimbles_confluence
            infinity_mat= self.infinity_loops*self.thimbles_confluence
            sing_comps = matrix(flatten(self.singular_components))*self.homology_smoothing
            if sing_comps ==0:
                mattot = block_matrix([[homology_mat], [infinity_mat]])
            else:
                mattot = block_matrix([[homology_mat], [infinity_mat], [sing_comps]])

            coefs = mattot.solve_left(self.homology_smoothing)
            periods_tot = vector(list(self.period_matrix.row(0)) + [0]*(self.infinity_loops.nrows() + len(flatten(self.singular_components))+2))

            self._periods_smoothing = matrix(block_diagonal_matrix([coefs, identity_matrix(2)])*periods_tot)
        return self._periods_smoothing

    @property
    def simple_periods(self):
        if not hasattr(self, '_simple_periods'):
            self._simple_periods = matrix(self.integrated_thimbles([0]))*self.homology.transpose()
        return self._simple_periods

    @property
    def P(self):
        return self._P

    @property
    def picard_fuchs_equation(self):
        if not hasattr(self,'_picard_fuchs_equation'):
            self._picard_fuchs_equation = self._family.picard_fuchs_equation(vector([1,0]))
        return self._picard_fuchs_equation
    
    @property
    def family(self):
        return self._family
    
    @property
    def discriminant(self):
        if not hasattr(self,'_discriminant'):
            flatPolRing = PolynomialRing(QQ, ['a','b','c','t'])
            [a,b,c,t] = flatPolRing.gens()
            weierstrass_coefs = WeierstrassForm(self.P(t,a,b,c), [a,b,c])
            Qt = PolynomialRing(QQ, 't')
            t = Qt.gens()[0]
            weierstrass_coefs =  [c(t=t) for c in weierstrass_coefs]
            self._discriminant=Qt(4*weierstrass_coefs[0](t=t)**3 + 27*weierstrass_coefs[1](t=t)**2)
        return self._discriminant
    
    @property
    def critical_points(self):
        if not hasattr(self,'_critical_points'):
            self._critical_points=self.discriminant.roots(QQbar, multiplicities=False)
            # self._critical_points=self.picard_fuchs_equation.leading_coefficient().roots(QQbar, multiplicities=False)
        return self._critical_points
    
    @property
    def monodromy_matrices(self):
        if not hasattr(self, '_monodromy_matrices'):
            assert self.picard_fuchs_equation.order()== len(self.family.basis),"Picard-Fuchs equation is not cyclic, cannot use it to compute monodromy"

            n = len(self.fiber.homology) 
            
            integration_correction = diagonal_matrix([1/ZZ(factorial(k)) for k in range(n+1)])
            derivatives_at_basepoint = self.derivatives_values_at_basepoint()
            initial_conditions = integration_correction* derivatives_at_basepoint
            initial_conditions = initial_conditions.submatrix(1,0)

            cohomology_monodromies = [initial_conditions**(-1)*M.submatrix(1,1)*initial_conditions for M in self.transition_matrices]


            Ms = [(self.fiber.period_matrix**(-1)*M*self.fiber.period_matrix) for M in cohomology_monodromies]
            if not self.ctx.debug:
                Ms = [M.change_ring(ZZ) for M in Ms]
            
            Mtot=1
            for M in Ms:
                Mtot=M*Mtot
            if Mtot!=identity_matrix(2):
                self._critical_points = self.critical_points+["infinity"]
                transition_matrix_infinity = 1
                for M in self.transition_matrices:
                    transition_matrix_infinity = M*transition_matrix_infinity
                self._transition_matrices += [transition_matrix_infinity**(-1)]
                Ms += [(Mtot**-1).change_ring(ZZ)]
                pathtot=[]
                for path in self.paths:
                    pathtot=pathtot+path
                self._paths+=[list(reversed(Util.simplify_path(pathtot)))]
            
            self._monodromy_matrices = Ms
        return self._monodromy_matrices
    
    @property
    def thimbles_confluence(self):
        if not hasattr(self, '_thimbles_confluence'):
            blocks =[]
            for i, pcs in enumerate(self.permuting_cycles):
                decompositions = []
                for p in pcs:
                    decomposition = []
                    for M, v in zip(self.monodromy_matrices_smoothing[i], self.vanishing_cycles_smoothing[i]):
                        decomposition += [(M-1)*p/v]
                        p = M*p
                    decompositions+=[decomposition]
                blocks+= [matrix(decompositions)]
            self._thimbles_confluence = block_diagonal_matrix(blocks).change_ring(ZZ)
        return self._thimbles_confluence

    @property
    def vanishing_cycles_smoothing(self):
        if not hasattr(self, '_vanishing_cycles_smoothing'):
            self._vanishing_cycles_smoothing = [[(M-1).transpose().image().gens()[0] for M in Ms] for Ms in self.monodromy_matrices_smoothing]
        return self._vanishing_cycles_smoothing
    
    @property
    def singular_components(self):
        if not hasattr(self, '_singular_components'):
            fullmat = block_matrix([[self.homology_smoothing], [self.infinity_loops*self.thimbles_confluence]])
            ranktot = 0
            rankmax = sum([len(Ms) for Ms in self.monodromy_matrices_smoothing])
            sing_comps = []
            for M in self.vanishing_cycles_smoothing:
                M = matrix(M)
                rank = M.dimensions()[0]
                sing_comps += [[vector([0]*ranktot+list(v) + [0]*(rankmax-ranktot-rank)) for v in M.kernel().gens()]]
                ranktot+=rank
            self._singular_components = [[fullmat.solve_left(component)[:-self.infinity_loops.nrows()] for component in components] for components in sing_comps]
        return self._singular_components

    
    @property
    def monodromy_matrices_smoothing(self):
        if not hasattr(self, '_monodromy_matrices_smoothing'):
            I1_monodromy_matrices = []
            for M in self.monodromy_matrices:
                type, base_change, nu = EllipticSingularities.monodromy_class(M)
                mats =  [base_change*M*base_change**-1 for M in EllipticSingularities.fibre_confluence[type][:-1]] + [base_change*EllipticSingularities.fibre_confluence[type][-1]*base_change**-1]*nu
                mats = [M.change_ring(ZZ) for M in mats]
                Mtot = 1
                for M2 in mats:
                    Mtot = M2*Mtot
                assert Mtot == M
                I1_monodromy_matrices += [mats]

            self._monodromy_matrices_smoothing = I1_monodromy_matrices

        return self._monodromy_matrices_smoothing

    @property
    def fiber(self):
        if not hasattr(self,'_fiber'):
            self._fiber = LefschetzFamily(self.P(self.basepoint), nbits=self.ctx.nbits)
            if self._fiber.intersection_product == matrix([[0,-1], [1,0]]):
                self._fiber._homology = list(reversed(self._fiber.homology))
                del self._fiber._intersection_product
            assert self._fiber.intersection_product == matrix([[0,1], [-1,0]])
        return self._fiber

    @property
    def thimbles(self):
        if not hasattr(self,'_thimbles'):
            self._thimbles=[]
            for pcs, path in zip(self.permuting_cycles, self.paths):
                for pc in pcs:
                    self._thimbles+=[(pc, path)]
        return self._thimbles

    @property
    def permuting_cycles(self):
        if not hasattr(self, '_permuting_cycles'):
            self._permuting_cycles = [[] for i in range(len(self.monodromy_matrices))]
            for i in range(len(self.monodromy_matrices)):
                M = self.monodromy_matrices[i]
                D, U, V = (M-1).smith_form()
                for j in range(2):
                    if D[j,j]!=0:
                        self._permuting_cycles[i] += [ V*vector([1 if k==j else 0 for k in range(2)]) ]
        return self._permuting_cycles
    
    @property
    def permuting_cycles_smoothing(self):
        if not hasattr(self, '_permuting_cycles_smoothing'):
            monodromy_matrices = flatten(self.monodromy_matrices_smoothing)
            vanishing = flatten(self.vanishing_cycles_smoothing)
            self._permuting_cycles_smoothing = []
            for i in range(len(monodromy_matrices)):
                M = monodromy_matrices[i]
                D, U, V = (M-1).smith_form()
                p = V.column(0)
                if (M-1)*p != vanishing[i]:
                    p = -p
                assert (M-1)*p == vanishing[i]
                self._permuting_cycles_smoothing += [ p ]
        return self._permuting_cycles_smoothing

    @property
    def borders_of_thimbles(self):
        if not hasattr(self, '_borders_of_thimbles'):
            self._borders_of_thimbles = []
            for ps, M in zip(self.permuting_cycles,self.monodromy_matrices):
                self._borders_of_thimbles += [(M-1)*p for p in ps]
        return self._borders_of_thimbles


    @property
    def infinity_loops(self):
        if not hasattr(self, '_infinity_loops'):
            infinity_cycles = []
            for i in range(2):
                v = vector([1 if k==i else 0 for k in range(2)])
                coefs = []
                for j in range(len(self.critical_points)):
                    M = self.monodromy_matrices[j]
                    if len(self.permuting_cycles[j])==0:
                        continue
                    coefs += list(matrix([(M-1)*t for t in self.permuting_cycles[j]]).solve_left((M-1)*v))
                    v = self.monodromy_matrices[j]*v
                infinity_cycles+=[vector(coefs)]
            self._infinity_loops = matrix(infinity_cycles)

        return self._infinity_loops
    
    @property
    def extensions_smoothing(self):
        if not hasattr(self, '_extensions_smoothing'):
            delta = matrix(flatten(self.vanishing_cycles_smoothing)).change_ring(ZZ)
            self._extensions_smoothing = delta.kernel()
        return self._extensions_smoothing
    
    @property
    def extensions(self):
        if not hasattr(self, '_extensions'):
            delta = matrix(self.borders_of_thimbles).change_ring(ZZ)
            self._extensions = delta.kernel()
        return self._extensions
    

    @property
    def homology(self):
        if not hasattr(self, '_homology'):
            r = len(self.monodromy_matrices)
            
            begin = time.time()
            # compute representatives of the quotient H(Y)/imtau
            D, U, V = self.extensions.matrix().smith_form()
            B = D.solve_left(self.infinity_loops*V).change_ring(ZZ)*U
            Brows=B.row_space()
            compl = [[0 for i in range(Brows.degree())]]
            rank=Brows.dimension()
            N=0
            for i in range(Brows.degree()):
                v=[1 if j==i else 0 for j in range(Brows.degree())]
                M=block_matrix([[B],[matrix(compl)],[matrix([v])]],subdivide=False)
                if rank+N+1==M.rank():
                    compl += [v]
                    N+=1
                if rank+N == Brows.degree():
                    break
            if len(compl)==1:
                self._homology = self.extensions.matrix().submatrix(0,0,0)
            else:
                quotient_basis=matrix(compl[1:])
                self._homology = quotient_basis*self.extensions.matrix()
            
            end = time.time()
            duration_str = time.strftime("%H:%M:%S",time.gmtime(end-begin))
            logger.info("[Elliptic Surface] Reconstructed homology from monodromy -- total time: %s."% (duration_str))
        return self._homology
   
    @property
    def homology_smoothing(self):
        if not hasattr(self, '_homology_smoothing'):
            begin = time.time()
            # compute representatives of the quotient H(Y)/imtau
            infinity_loops = self.infinity_loops*self.thimbles_confluence
            D, U, V = self.extensions_smoothing.matrix().smith_form()
            B = D.solve_left(infinity_loops*V).change_ring(ZZ)*U
            Brows=B.row_space()
            compl = [[0 for i in range(Brows.degree())]]
            rank=Brows.dimension()
            N=0
            for i in range(Brows.degree()):
                v=[1 if j==i else 0 for j in range(Brows.degree())]
                M=block_matrix([[B],[matrix(compl)],[matrix([v])]],subdivide=False)
                if rank+N+1==M.rank():
                    compl += [v]
                    N+=1
                if rank+N == Brows.degree():
                    break
            quotient_basis=matrix(compl[1:])
            self._homology_smoothing = quotient_basis*self.extensions_smoothing.matrix()
            
            end = time.time()
            duration_str = time.strftime("%H:%M:%S",time.gmtime(end-begin))
            logger.info("[Elliptic Surface] Reconstructed homology from monodromy -- total time: %s."% (duration_str))
        return self._homology_smoothing


    @property
    def transition_matrices(self):
        if not hasattr(self, '_transition_matrices'):
            L = self.picard_fuchs_equation
            L = L* L.parent().gens()[0]
            self._transition_matrices = self.integrate(L)
        return self._transition_matrices
    
    def integrate(self, L):
        logger.info("[Elliptic Surface] Computing numerical transition matrices of operator of order %d and degree %d (%d edges total)."% (L.order(), L.degree(), len(self.fundamental_group.edges)))
        begin = time.time()

        integrator = Integrator(self.fundamental_group, L, self.ctx.nbits)
        transition_matrices = integrator.transition_matrices
        
        end = time.time()
        duration_str = time.strftime("%H:%M:%S",time.gmtime(end-begin))
        logger.info("[Elliptic Surface] Integration finished -- total time: %s."% (duration_str))

        return transition_matrices

    def forget_transition_matrices(self):
        del self._transition_matrices
        del self._integrated_thimbles
        
    @property
    def integrated_thimbles(self):
        if not hasattr(self, '_integrated_thimbles'):
        
            s=len(self.fiber.homology)
            r=len(self.thimbles)

            transition_matrices= self.transition_matrices

            derivatives_at_basepoint = self.derivatives_values_at_basepoint()
            integration_correction = diagonal_matrix([1/ZZ(factorial(k)) for k in range(s+1)])
            pM = self.fiber.period_matrix
            initial_conditions = integration_correction* derivatives_at_basepoint*pM
            _integrated_thimbles = []
            for i,ps in enumerate(self.permuting_cycles):
                _integrated_thimbles += [(transition_matrices[i]*initial_conditions*p)[0] for p in ps]
            self._integrated_thimbles = _integrated_thimbles
        return self._integrated_thimbles
    
    # Integration methods

    def derivatives_coordinates(self, i):
        if not hasattr(self, '_coordinates'):
            s=len(self.fiber.homology)
            
            w = self.P.parent()(1)
            derivatives = [self.P.parent()(0), w]
            for k in range(s-1):
                derivatives += [self._derivative(derivatives[-1], self.P)] 
            self._coordinates = self.family.coordinates(derivatives)

        return self._coordinates[i]


    def derivatives_values_at_basepoint(self):
        s=len(self.fiber.homology)

        w = self.P.parent()(1)
        derivatives = [self.P.parent()(0), w]
        for k in range(s-1):
            derivatives += [self._derivative(derivatives[-1], self.P)] 
        return self.family._coordinates(derivatives, self.basepoint)

    def _compute_intersection_product(self):
        r=len(flatten(self.vanishing_cycles_smoothing))
        inter_prod_thimbles = matrix([[self._compute_intersection_product_thimbles(i,j) for j in range(r)] for i in range(r)])
        intersection_11 = (-1) * (self.homology_smoothing*inter_prod_thimbles*self.homology_smoothing.transpose()).change_ring(ZZ)
        intersection_02 = matrix(ZZ, [[0,1],[1,-2]])
        return block_diagonal_matrix(intersection_11, intersection_02)
        
    def _compute_intersection_product_thimbles(self,i,j):
        vi = self.permuting_cycles_smoothing[i]
        Mi = flatten(self.monodromy_matrices_smoothing)[i]
        vj = self.permuting_cycles_smoothing[j]
        Mj = flatten(self.monodromy_matrices_smoothing)[j]

        di, dj = ((Mi-1)*vi), (Mj-1)*vj

        
        res = di*self.fiber.intersection_product*dj
        resid = -vi*self.fiber.intersection_product*di

        if i==j:
            return resid
        if i<j:
            return res
        else:
            return 0

    @classmethod
    def _derivative(self, A, P): 
        """computes the numerator of the derivative of A/P^k"""
        field = P.parent()
        return field(A).derivative() - A*P.derivative()         

    @property
    def fundamental_group(self):
        if not hasattr(self,'_fundamental_group'):
            begin = time.time()

            fundamental_group = FundamentalGroupVoronoi(self.critical_points, self.basepoint) # access future delaunay implem here
            fundamental_group.sort_loops()

            end = time.time()
            duration_str = time.strftime("%H:%M:%S",time.gmtime(end-begin))
            logger.info("[Elliptic Surface] Fundamental group computed in %s."% (duration_str))

            self._critical_points = fundamental_group.points[1:]
            self._fundamental_group = fundamental_group
        return self._fundamental_group

    @property
    def paths(self):
        if not hasattr(self,'_paths'):
            paths = []
            for path in self.fundamental_group.pointed_loops:
                paths += [[self.fundamental_group.vertices[v] for v in path]]
            self._paths= paths
        return self._paths

    @property
    def basepoint(self):
        if  not hasattr(self, '_basepoint'):
            shift = 1
            reals = [self.ctx.CF(c).real() for c in self.critical_points]
            xmin, xmax = min(reals), max(reals)
            self._basepoint = Util.simple_rational(xmin - (xmax-xmin)*shift, (xmax-xmin)/10)
        return self._basepoint

    @property
    def neron_severi(self):
        if  not hasattr(self, '_neron_severi'):
            self._neron_severi = IntegerRelations(self.periods_smoothing.transpose()).basis.rows()
        return self._neron_severi
    
    @property
    def transcendental_lattice(self):
        if  not hasattr(self, '_transcendental_lattice'):
            IL = IntegralLattice(self.intersection_product)
            self._transcendental_lattice = IL.orthogonal_complement(self.neron_severi).basis()
        return self._transcendental_lattice

    @property
    def trivial_lattice(self):
        if  not hasattr(self, '_trivial_lattice'):
            singular_components = matrix(flatten(self.singular_components))
            singular_components = block_matrix([[singular_components,zero_matrix(singular_components.nrows(), 2)]])
            self._trivial_lattice = singular_components.rows() + identity_matrix(self.homology_smoothing.nrows()+2).rows()[-2:]
        return self._trivial_lattice
    
    @property
    def mordell_weyl(self):
        if  not hasattr(self, '_mordell_weyl'):
            NS = matrix(self.neron_severi).image()
            Triv = NS.submodule(self.trivial_lattice)
            self._mordell_weyl = NS/TL
        return self._mordell_weyl

