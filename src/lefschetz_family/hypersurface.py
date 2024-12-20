# -*- coding: utf-8 -*-

import sage.all

from .numperiods.family import Family
from .numperiods.cohomology import Cohomology
from .numperiods.integerRelations import IntegerRelations
from ore_algebra import *

from sage.modules.free_module_element import vector
from sage.rings.complex_arb import ComplexBallField
from sage.rings.polynomial.polynomial_ring_constructor import PolynomialRing
from sage.rings.rational_field import QQ
from sage.rings.qqbar import AlgebraicField
from sage.rings.qqbar import QQbar
from sage.functions.other import factorial
from sage.matrix.constructor import matrix
from sage.arith.misc import xgcd
from sage.rings.integer_ring import ZZ
from sage.matrix.special import identity_matrix
from sage.matrix.special import diagonal_matrix
from sage.matrix.special import block_matrix
from sage.matrix.special import block_diagonal_matrix
from sage.matrix.special import zero_matrix
from sage.arith.functions import lcm
from sage.quadratic_forms.quadratic_form import QuadraticForm

from ore_algebra.analytic.differential_operator import DifferentialOperator


from sage.misc.prandom import randint

from .voronoi import FundamentalGroupVoronoi
from .integrator_simultaneous import IntegratorSimultaneous
from .integrator import Integrator
from .util import Util
from .context import Context
from .exceptionalDivisorComputer import ExceptionalDivisorComputer
from .delaunayDual import FundamentalGroupDelaunayDual

import logging
import time

logger = logging.getLogger(__name__)


class Hypersurface(object):
    def __init__(self, P, fibration=None, compute_fundamental_group=True, **kwds):
        """P, a homogeneous polynomial defining a smooth hypersurface X in P^{n+1}.

        This class aims at computing an effective basis of the homology group H_n(X), 
        given as lifts of paths through a Lefschetz fibration.
        """
        
        self.ctx = Context(**kwds)
        
        # assert P.is_homogeneous(), "nonhomogeneous defining polynomial"
        
        self._P = P
        if fibration != None:
            assert matrix(fibration).rank() == len(fibration), "collection of hyperplanes is not generic"
            assert len(fibration) == self.dim+1, "fibration does not have the correct number of hyperplanes"
            self._fibration = fibration
        if self.dim>=1 and not self.ctx.debug:
            fg = self.fundamental_group # this allows reordering the critical points straight away and prevents shenanigans. There should be a better way to do this
    
    
    @property
    def intersection_product_modification(self):
        """The intersection matrix of the modification of the hypersurface"""
        if not hasattr(self,'_intersection_product_modification'):
            assert self.dim!=0, "no modification in dimension 0"
            self._intersection_product_modification=self._compute_intersection_product_modification()
        return self._intersection_product_modification
    
    @property
    def intersection_product(self):
        """The intersection matrix of the hypersurface"""
        if not hasattr(self,'_intersection_product'):
            if self.dim==0:
                self._intersection_product=identity_matrix(self.degree)
            elif self.dim==1:
                self._intersection_product=self.intersection_product_modification
            else:
                homology = matrix(self.homology)
                IP = homology*self.intersection_product_modification*homology.transpose()
                assert IP.det() in [1,-1], "intersection product is not unitary"
                self._intersection_product = IP
        return self._intersection_product

    @property
    def homology(self):
        """An embedding of the homology of the hypersurface in the homology of the modification."""
        if not hasattr(self,'_homology'):
            if self.dim<2:
                self._homology = identity_matrix(len(self.extensions)).rows()
            else:
                product_with_exdiv = self.intersection_product_modification*matrix(self.exceptional_divisors).transpose()
                product_with_exdiv = product_with_exdiv.change_ring(ZZ)
                self._homology = product_with_exdiv.kernel().basis()
        return self._homology

    @property
    def period_matrix_modification(self):
        """The period matrix of the modification of the hypersurface"""
        if not hasattr(self, '_period_matrix_modification'):
            integrated_thimbles = self.integrated_thimbles
            add = [vector([0]*len(self.thimbles))]*2 if self.dim%2 ==0 else []
            homology_mat = matrix(self.extensions + add).transpose()
            self._period_matrix_modification = integrated_thimbles * homology_mat
        return self._period_matrix_modification

    @property
    def period_matrix(self):
        """The period matrix of the hypersurface"""
        if not hasattr(self, '_period_matrix'):
            if self.dim==0:
                R = self.P.parent()
                affineR = PolynomialRing(QQbar, 'X')
                affineProjection = R.hom([affineR.gens()[0],1], affineR)
                CBF = ComplexBallField(self.ctx.nbits)
                period_matrix = matrix([self._residue_form(affineProjection(b), affineProjection(self.P), (b.degree()+len(R.gens()))//self.P.degree(), self.extensions) for b in self.cohomology]).change_ring(CBF)
                period_matrix = block_matrix([[period_matrix],[matrix([[CBF(1)]*self.degree])]])
                self._period_matrix=period_matrix
            elif self.dim%2 ==1:
                self._period_matrix = self.period_matrix_modification*matrix(self.homology).transpose()
            else:
                self._period_matrix = block_matrix([[self.period_matrix_modification*matrix(self.homology).transpose()], [matrix(self.intersection_product*self.lift_modification(self.fibre_class))]])
        return self._period_matrix
    
    @property
    def holomorphic_periods_modification(self):
        """The holomorphic period matrix of the modification of the hypersurface"""
        if not hasattr(self, '_holomorphic_periods_modification'):
            if self.dim==0:
                self._holomorphic_periods_modification = self.period_matrix
            else:
                integrated_thimbles_holomorphic = self.integrated_thimbles_holomorphic
                add = [vector([0]*len(self.thimbles))]*2 if self.dim%2 ==0 else []
                homology_mat = matrix(self.extensions + add).transpose()
                self._holomorphic_periods_modification =  integrated_thimbles_holomorphic * homology_mat
        return self._holomorphic_periods_modification
    @property
    def holomorphic_periods(self):
        """The holomorphic period matrix of the hypersurface"""
        if not hasattr(self, '_holomorphic_periods'):
            if self.dim==0:
                self._holomorphic_periods=self.period_matrix
            else:
                self._holomorphic_periods = self.holomorphic_periods_modification*matrix(self.homology).transpose()
        return self._holomorphic_periods

    @property
    def holomorphic_forms(self):
        """The holomorphic cohomology classes."""
        if not hasattr(self, "_holomorphic_forms"):
            mindeg = min([m.degree() for m in self.cohomology])
            self._holomorphic_forms = [m for m in self.cohomology if m.degree()==mindeg]
        return self._holomorphic_forms


    @property
    def P(self):
        """The defining equation of the hypersurface."""
        return self._P

    @property
    def degree(self):
        if not hasattr(self,'_degree'):
            self._degree = self.P.degree()
        return self._degree
    
    @property
    def dim(self):
        if not hasattr(self,'_dim'):
            self._dim = len(self.P.parent().gens())-2
        return self._dim
    
    @property
    def cohomology(self):
        if not hasattr(self,'_cohomology'):
            self._cohomology = Cohomology(self.P).basis()
        return self._cohomology
    
    
    @property
    def family(self):
        if not hasattr(self,'_family'):
            RtoS = self._RtoS()
            self._family = Family(RtoS(self.P))
        return self._family
    

    @property
    def fibration(self):
        if not hasattr(self,'_fibration'): #TODO try to reduce variance of distance between critical points(?)
            rank = self.dim+1 if self.ctx.long_fibration else 2
            
            r=0
            fibration = []
            for r in range(rank):
                while True:
                    v = vector([randint(-10,10) for i in range(self.dim+2)])
                    if v not in matrix(fibration).image():
                        fibration += [v]
                        break
            self._fibration = fibration
        return self._fibration

    @property
    def critical_values(self):
        if not hasattr(self,'_critical_values'):
            R = self.P.parent()
            _vars = [v for v in R.gens()]
            forms=[v.dot_product(vector(_vars)) for v in self.fibration[:2]]
            f=forms[0]/forms[1]
            S = PolynomialRing(QQ, _vars+['k','t'])
            k,t= S.gens()[-2:]
            eqs = [
                self.P, 
                forms[1]-1, 
                t*forms[1]-forms[0]
            ] + [(f.derivative(var).numerator()*k-self.P.derivative(var)*f.derivative(var).denominator()) for var in _vars]

            ideal = S.ideal(eqs).elimination_ideal(S.gens()[:-1])
            Qt = PolynomialRing(QQ, 't')

            roots_with_multiplicity = Qt(ideal.groebner_basis()[0]).roots(AlgebraicField())
            if not self.ctx.debug:
                for e in roots_with_multiplicity:
                    assert e[1]==1, "double critical values, fibration is not Lefschetz"
            self._critical_values=[e[0] for e in roots_with_multiplicity]
        return self._critical_values
    
    @property
    def monodromy_matrices(self):
        assert self.dim!=0, "Cannot compute monodromy matrices in dimension 0"
        if not hasattr(self, '_monodromy_matrices'):
            i=0
            transition_matrices = self.transition_matrices_monodromy

            n = len(self.fiber.homology) 
            R = len(self.cohomology)
            
            cohomology_fiber_to_family = self.family._coordinates([self.family.pol.parent()(w) for w in self.fiber.cohomology], self.basepoint)
            initial_conditions = cohomology_fiber_to_family.inverse()

            cohomology_monodromies = [initial_conditions.inverse() * M * initial_conditions for M in transition_matrices]
            if self.dim%2==1:
                cohomology_monodromies = [block_diagonal_matrix([M, identity_matrix(1)]) for M in cohomology_monodromies]

            Ms = [(self.fiber.period_matrix.inverse() * M * self.fiber.period_matrix) for M in cohomology_monodromies]
            if not self.ctx.debug:
                Ms = [M.change_ring(ZZ) for M in Ms]
            if not self.ctx.singular and not self.ctx.debug:
                for M in Ms:
                    assert (M-1).rank()==1, "If M is a monodromy matrix around a single critical point, M-I should have rank 1"
            
            self._monodromy_matrices = Ms
        return self._monodromy_matrices
    
    @property
    def fiber(self):
        assert self.dim!=0, "Variety of dimension 0 does not have a fiber"
        if not hasattr(self,'_fiber'):
            RtoS = self._RtoS()
            evaluate_at_basepoint = RtoS.codomain().hom([self.basepoint], RtoS.codomain().base_ring())
            P = evaluate_at_basepoint(RtoS(self.P))
            fibration  = self._restrict_fibration() if self.ctx.long_fibration else None
            self._fiber = Hypersurface(P, fibration = fibration, method=self.ctx.method, nbits=self.ctx.nbits, long_fibration=self.ctx.long_fibration, depth=self.ctx.depth+1, simultaneous_integration=True)

        return self._fiber

    @property
    def thimbles(self):
        if not hasattr(self,'_thimbles'):
            res = []
            for pc, path in zip(self.permuting_cycles, self.paths):
                res += [(pc, path)]
            self._thimbles = res
        return self._thimbles

    @property
    def permuting_cycles(self):
        if not hasattr(self, '_permuting_cycles'):
            self._permuting_cycles = [None for i in range(len(self.monodromy_matrices))]
            for i in range(len(self.monodromy_matrices)):
                M = self.monodromy_matrices[i]
                D, U, V = (M-1).smith_form()
                self._permuting_cycles[i] = V * vector([1]+[0]*(V.dimensions()[0]-1))
        return self._permuting_cycles

    @property
    def vanishing_cycles(self):
        if not hasattr(self, '_vanishing_cycles'):
            self._vanishing_cycles = []
            for p, M in zip(self.permuting_cycles,self.monodromy_matrices):
                self._vanishing_cycles += [(M-1)*p]
        return self._vanishing_cycles


    @property
    def infinity_loops(self):
        if not hasattr(self, '_infinity_loops'):
            Mtot=1
            phi=[]
            for M, v in zip(self.monodromy_matrices, self.vanishing_cycles):
                tempM=(M-1)*Mtot
                phi+=[[c/v for c in tempM.columns()]]
                Mtot=M*Mtot
            phi = matrix(phi).transpose().change_ring(ZZ)
            if not self.ctx.debug:
                assert Mtot == identity_matrix(len(self.fiber.homology)), "Monodromy around infinity is nontrivial, most likely because the paths do not actually compose to the loop around infinity"
            self._infinity_loops = phi.rows()

        return self._infinity_loops
    
    @property
    def kernel_boundary(self):
        if not hasattr(self, '_kernel_boundary'):
            delta = matrix(self.vanishing_cycles).change_ring(ZZ)
            self._kernel_boundary = delta.kernel()

        return self._kernel_boundary
    

    @property
    def extensions(self):
        if not hasattr(self, '_extensions'):
            if self.dim==0:
                R = self.P.parent()
                affineR = PolynomialRing(QQbar, 'X')
                affineProjection = R.hom([affineR.gens()[0],1], affineR)
                self._extensions = [e[0] for e in affineProjection(self.P).roots()]

            else:
                r = len(self.monodromy_matrices)
                
                begin = time.time()
                # compute representants of the quotient H(Y)/imtau
                D, U, V = self.kernel_boundary.matrix().smith_form()
                B = D.solve_left(matrix(self.infinity_loops)*V).change_ring(ZZ)*U
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
                self._extensions = (quotient_basis*self.kernel_boundary.matrix()).rows() # NB this is the homology of Y, to recover the homology of X we need to remove the kernel of the period matrix
                
                end = time.time()
                duration_str = time.strftime("%H:%M:%S",time.gmtime(end-begin))
                logger.info("[%d] Reconstructed homology from monodromy -- total time: %s."% (self.dim, duration_str))

        return self._extensions

    @property
    def thimble_extensions(self):
        """Returns a list of elements of the form `[boundary, extension]` such that `extension` is the extension of a thimble of the fiber of the fiber along the loop around infinity. 
        `boundary` is the boundary of the extended thimble. 
        The list consisting of the `boundary`s forms a basis of the image of the boundary map.
        `extension` if defined only up to an infinity loop."""
        if not hasattr(self, '_thimble_extensions'):
            if self.dim<2:
                self._thimble_extensions = []
            else:
                distinct_vanishing_cycles = []
                for i, v in enumerate(self.fiber.vanishing_cycles):
                    if v not in matrix([self.fiber.vanishing_cycles[j] for j in distinct_vanishing_cycles]).image():
                        distinct_vanishing_cycles+=[i]
                        
                chains = [self.fiber.vanishing_cycles[i] for i in distinct_vanishing_cycles]

                thimble_extensions = zero_matrix(len(distinct_vanishing_cycles),len(self.thimbles))
                for j in distinct_vanishing_cycles:
                    u=vector([0]*len(self.fiber.thimbles))
                    u[j]=1
                    for i, M in enumerate(self.thimble_monodromy):
                        v = (M-1)*u
                        v = self.fiber.lift(v)
                        u = M*u
                        c = v/self.vanishing_cycles[i]
                        thimble_extensions[j,i] = c
                thimble_extensions = thimble_extensions.rows()
                self._thimble_extensions = list(zip(chains, thimble_extensions))
        return self._thimble_extensions

    @property
    def thimble_monodromy(self):
        if not hasattr(self, "_thimble_monodromy"):
            logger.info("[%d] Computing thimble monodromy with braids, this may take a while."% self.dim)
            begin = time.time()
            self._EDC = ExceptionalDivisorComputer(self)
            self._thimble_monodromy = self._EDC.thimble_monodromy
            end = time.time()
            duration_str = time.strftime("%H:%M:%S",time.gmtime(end-begin))
            logger.info("Thimble monodromy computed in %s.", duration_str)
        return self._thimble_monodromy
    
    @property
    def invariant(self): # TODO : in dim >0 this is just the fibre. 
        if not hasattr(self, '_invariant'):
            self._invariant = vector(Util.find_complement(matrix([chain for chain, _ in self.thimble_extensions])))
        return self._invariant

    @property
    def exceptional_divisors(self):
        """Returns the coordinates of the exceptional divisors in the basis of homology of the modification."""
        if not hasattr(self, '_exceptional_divisors'):
            if self.dim==2 and self.degree in [3,4]: # this is specific for K3 surfaces, while waiting for more robust/efficient methods arrive for the general case
                if self.degree ==4:
                    NS = IntegerRelations(self.holomorphic_periods_modification.transpose()).basis
                if self.degree==3:
                    NS = IntegerRelations(self.period_matrix_modification.transpose()).basis
                section = self.section
                fibre = self.fibre_class
                others = (NS*self.intersection_product_modification*matrix([section, fibre]).transpose()).kernel().basis_matrix()
                short_vectors = QuadraticForm(-2 * others * NS * self.intersection_product_modification * NS.transpose() * others.transpose()).short_vector_list_up_to_length(3)[2]
                short_vectors = [v*others*NS for v in short_vectors]
                exp_divs = [v+section+fibre for v in short_vectors]
                chosen=[]
                while len(exp_divs)!=0:
                    chosen += [exp_divs[0]]
                    exp_divs = [v for v in exp_divs if v * self.intersection_product_modification*chosen[-1]==0]
                self._exceptional_divisors = chosen + [self.section]

            else:
                if self.dim%2 ==1:
                    exceptional_divisors = [self.lift(extension) for _, extension in self.thimble_extensions]
                    chains = matrix([chain for chain, _ in self.thimble_extensions])
                else:
                    exceptional_divisors = []
                    for chain, extension in self.thimble_extensions:
                        exceptional_divisor = self.lift(extension)
                        exceptional_divisor -= self.fibre_class * (chain*self.fiber.fiber.intersection_product*self.invariant)
                        exceptional_divisors += [exceptional_divisor]
                    exceptional_divisors += [self.section]
                    chains = matrix([chain for chain, _ in self.thimble_extensions] + [self.invariant])
                self._exceptional_divisors = (chains**(-1)*matrix(exceptional_divisors)).rows()
        return self._exceptional_divisors

    @property
    def _restriction_variable(self):
        if not hasattr(self, "__restriction_variable"):
            for i in range(self.dim+2):
                if self.fibration[0][i] !=0:
                    break
            self.__restriction_variable = i # type: ignore
        return self.__restriction_variable

    def _RtoS(self):
        R = self.P.parent()

        a = self.fibration[1][self._restriction_variable]
        b = self.fibration[0][self._restriction_variable]

        _vars = [v for v in R.gens()]
        S = PolynomialRing(PolynomialRing(QQ, [_vars[i] for i in range(len(_vars)) if i != self._restriction_variable]), 't')
        t=S.gens()[0]

        l = vector([c for i, c in enumerate(_vars) if i != self._restriction_variable])*vector([c for i,c in enumerate(self.fibration[0]) if i != self._restriction_variable])
        m = vector([c for i, c in enumerate(_vars) if i != self._restriction_variable])*vector([c for i,c in enumerate(self.fibration[1]) if i != self._restriction_variable])

        form = (-S(l)+t*S(m))
        denom = b-a*t

        RtoS = R.hom([denom*S(_vars[i]) if i != self._restriction_variable else form for i in range(len(_vars))], S)
        return RtoS
    
    def _restrict_fibration(self):
        a = self.fibration[1][self._restriction_variable]
        b = self.fibration[0][self._restriction_variable]
        
        l = vector([c for i, c in enumerate(self.fibration[0]) if i != self._restriction_variable])
        m = vector([c for i, c in enumerate(self.fibration[1]) if i != self._restriction_variable])

        form = -l+self.basepoint*m
        
        hyperplanes = []
        for hyperplane in self.fibration[1:]:
            cs = (b-a*self.basepoint) * vector([c for i, c in enumerate(hyperplane) if i != self._restriction_variable])
            cz = hyperplane[self._restriction_variable]*form
            hyperplanes += [cs+cz]
        return hyperplanes

    def _restrict_form(self, A):
        """ Given a form A, returns the form A_t such that A/P^k w_n = A_t/P_t^k w_{n-1}dt
        """
        assert self.dim !=0, "cannot restrict form of a dimension 0 variety"

        RtoS = self._RtoS()


        R = self.P.parent()

        a = self.fibration[1][self._restriction_variable]
        b = self.fibration[0][self._restriction_variable]

        _vars = [v for v in R.gens()]
        S = PolynomialRing(PolynomialRing(QQ, [_vars[i] for i in range(len(_vars)) if i != self._restriction_variable]), 't')
        t=S.gens()[0]

        l = vector([_vars[i] for i in range(len(_vars)) if i != self._restriction_variable])*vector([self.fibration[0][i] for i in range(len(_vars)) if i != self._restriction_variable])
        m = vector([_vars[i] for i in range(len(_vars)) if i != self._restriction_variable])*vector([self.fibration[1][i] for i in range(len(_vars)) if i != self._restriction_variable])

        form = (-S(l)+t*S(m))
        denom = b-a*t

        dt = (-a * S(l) +b* S(m))*denom**(self.dim)
        return RtoS(A)*dt

    @property
    def transition_matrices(self):
        if not hasattr(self, '_transition_matrices'):
            if hasattr(self, '_transition_matrices_holomorphic') and len(self.holomorphic_forms) == len(self.cohomology):
                self._transition_matrices = self.transition_matrices_holomorphic
                return self._transition_matrices

            if hasattr(self, '_transition_matrices_holomorphic'):
                rat_coefs = self.family.coordinates([self._restrict_form(w) for w in self.cohomology if w not in self.holomorphic_forms])
            else:
                rat_coefs = self.family.coordinates([self._restrict_form(w) for w in self.cohomology])

            logger.info("[%d] Computing transition matrices of all forms (%d rational vector(s))."% (self.dim, rat_coefs[0].nrows()))
            if rat_coefs[0].nrows() > self.ctx.cutoff_simultaneous_integration:
                transition_matrices = self._compute_transition_matrices_simultaneous(rat_coefs)
            else:
                indices = [i for i in range(len(self.cohomology))]
                transition_matrices = self._compute_transition_matrices_sequential(rat_coefs, indices)
            self._transition_matrices = transition_matrices
        return self._transition_matrices

    @property
    def transition_matrices_holomorphic(self):
        if not hasattr(self, '_transition_matrices_holomorphic'):
            if hasattr(self, '_transition_matrices') or self.ctx.simultaneous_integration:
                r = self.fiber.period_matrix.nrows()
                R = len(self.cohomology)
                indices = [self.cohomology.index(w) for w in self.holomorphic_forms]
                indices += [R+i for i in range(r)]
                transition_matrices = [M.matrix_from_rows_and_columns(indices, indices) for M in self.transition_matrices]
            else:
                logger.info("[%d] Computing transition matrices for holomorphic_forms (%d rational vector(s))."% (self.dim, rat_coefs[0].nrows()))
                rat_coefs = self.family.coordinates([self._restrict_form(w) for w in self.holomorphic_forms])
                if rat_coefs[0].nrows() > self.ctx.cutoff_simultaneous_integration:
                    transition_matrices = self._compute_transition_matrices_simultaneous(rat_coefs)
                else:
                    indices = [i for i in range(len(self.holomorphic_forms))]
                    transition_matrices = self._compute_transition_matrices_sequential(rat_coefs, indices)
            self._transition_matrices_monodromy = transition_matrices
        return self._transition_matrices_holomorphic

    @property
    def transition_matrices_monodromy(self): # this function might very well be buggy, but it's not called very often.
        if not hasattr(self, '_transition_matrices_monodromy'):
            if hasattr(self, '_transition_matrices') or self.ctx.simultaneous_integration:
                r = self.fiber.period_matrix.nrows()
                R = len(self.cohomology)
                transition_matrices = [M.submatrix(R,R) for M in self.transition_matrices]
            elif hasattr(self, '_transition_matrices_holomorphic'):
                r = self.fiber.period_matrix.nrows()
                R = len(self.holomorphic_forms)
                transition_matrices = [M.submatrix(R,R) for M in self.transition_matrices_holomorphic]
            else:
                indices = [0]
                rat_coefs = self.family.coordinates([self._restrict_form(self.cohomology[0])])
                logger.info("[%d] Computing transition matrices for monodromy (%d rational vector(s))."% (self.dim, rat_coefs[0].nrows()))
                transition_matrices = self._compute_transition_matrices_sequential(rat_coefs, indices)
                transition_matrices = [M.submatrix(1,1) for M in transition_matrices]
            self._transition_matrices_monodromy = transition_matrices
        return self._transition_matrices_monodromy

    def _compute_transition_matrices_simultaneous(self, rat_coefs):
        gaussmanin = self.family.gaussmanin()
        logger.info("[%d] Computing numerical transition matrices for %d integrals (%d edges total)."% (self.dim, rat_coefs[0].nrows(), len(self.fundamental_group.edges)))
        begin = time.time()
        integrator = IntegratorSimultaneous(self.fundamental_group, rat_coefs, gaussmanin, self.ctx.nbits)
        transition_matrices = integrator.transition_matrices
        if hasattr(self, '_transition_matrices_holomorphic'):
            Rholo = len(self.holomorphic_forms)
            R = len(self.cohomology) - Rholo
            r = len(self.fiber.cohomology)
            intold = [M.submatrix(0,Rholo,Rholo,r) for M in self.transition_matrices_holomorphic]
            intnew = [M.submatrix(0,R,R,r) for M in transition_matrices]
            GM = [M.submatrix(R,R) for M in transition_matrices]
            transition_matrices = [block_matrix([[1,0, a],[0,1, b], [0,0,c]]) for a,b,c in zip(intold, intew, GM)]
        end = time.time()
        duration_str = time.strftime("%H:%M:%S",time.gmtime(end-begin))
        logger.info("[%d] Integration finished -- total time: %s."% (self.dim, duration_str))
        return transition_matrices

    @property
    def integrated_thimbles(self):
        if not hasattr(self, '_integrated_thimbles'):
            s=len(self.fiber.homology)
            R=len(self.cohomology)
            r=len(self.thimbles)
            
            integration_correction = diagonal_matrix([1/ZZ(factorial(k)) for k in range(s if self.dim%2==1 else s+1)])
            pM = self.fiber.period_matrix
            if self.dim%2==1:
                pM = pM.submatrix(0,0,s-1)
            expand = zero_matrix(R,s-1 if self.dim%2==1 else s).stack(identity_matrix(s-1 if self.dim%2==1 else s))
            self._integrated_thimbles = matrix([(self.transition_matrices[j]*expand*pM*self.permuting_cycles[j])[:R] for j in range(r)]).transpose()
        return self._integrated_thimbles
    
    @property
    def integrated_thimbles_holomorphic(self):
        if not hasattr(self, '_integrated_thimbles_holomorphic'):
            s=len(self.fiber.homology)
            R=len(self.holomorphic_forms)
            r=len(self.thimbles)
            
            integration_correction = diagonal_matrix([1/ZZ(factorial(k)) for k in range(s if self.dim%2==1 else s+1)])
            pM = self.fiber.period_matrix
            if self.dim%2==1:
                pM = pM.submatrix(0,0,s-1)
            expand = zero_matrix(R,s-1 if self.dim%2==1 else s).stack(identity_matrix(s-1 if self.dim%2==1 else s))
            self._integrated_thimbles_holomorphic = matrix([(self.transition_matrices_holomorphic[j]*expand*pM*self.permuting_cycles[j])[:R] for j in range(r)]).transpose()
        return self._integrated_thimbles_holomorphic

    def _compute_intersection_product_modification(self):
        r=len(self.thimbles)
        inter_prod_thimbles = matrix([[self._compute_intersection_product_thimbles(i,j) for j in range(r)] for i in range(r)])
        intersection_11 = (-1)**(self.dim-1) * (matrix(self.extensions)*inter_prod_thimbles*matrix(self.extensions).transpose()).change_ring(ZZ)
        if self.dim%2==0:
            intersection_02 = zero_matrix(2,2)
            intersection_02[0,1], intersection_02[1,0] = 1,1
            intersection_02[1,1] = -1
            return block_diagonal_matrix(intersection_11, intersection_02)
        else:
            return intersection_11
        
    def _compute_intersection_product_thimbles(self, i, j):
        vi = self.thimbles[i][0]
        Mi = self.monodromy_matrices[i]
        vj = self.thimbles[j][0]
        Mj = self.monodromy_matrices[j]

        di, dj = ((Mi-1)*vi), (Mj-1)*vj

        
        res = di*self.fiber.intersection_product*dj
        resid = -vi*self.fiber.intersection_product*di

        if i==j:
            return resid
        if i<j:
            return res
        else:
            return 0
    
    def _residue_form(self, A, P, k, alphas): 
        """ returns the formal residue of A/P^k at alpha for alpha in alphas """
        G,U,V = xgcd(P, P.derivative())
        assert G==1, "P is not squarefree"
        if k==1:
            return [V(alpha)*A(alpha) for alpha in alphas]
        return self._residue_form(A*U/(k-1)+(A*V).derivative()/(k-1)**2, P, k-1, alphas)

    @property
    def fundamental_group(self):
        assert self.dim>0, "Dimension 0 vartiety has no fibration"
        if not hasattr(self,'_fundamental_group'):
            logger.info("[%d] Computing fundamental group with %d critical values."% (self.dim, len(self.critical_values)))
            begin = time.time()
            if self.ctx.method == 'voronoi':# access future delaunay implem here
                fundamental_group = FundamentalGroupVoronoi(self.critical_values, self.basepoint)
            elif self.ctx.method == 'delaunay_dual':
                fundamental_group = FundamentalGroupDelaunayDual(self.critical_values, self.basepoint)
            else:
                fundamental_group = FundamentalGroupVoronoi(self.critical_values, self.basepoint)
            fundamental_group.sort_loops()

            end = time.time()
            duration_str = time.strftime("%H:%M:%S",time.gmtime(end-begin))
            logger.info("[%d] Fundamental group computed in %s."% (self.dim, duration_str))

            self._critical_values = fundamental_group.points[1:]
            self._fundamental_group = fundamental_group
        return self._fundamental_group

    @property
    def paths(self):
        assert self.dim>0, "Dimension 0 vartiety has no fibration"
        if not hasattr(self,'_paths'):
            paths = []
            for path in self.fundamental_group.pointed_loops:
                paths += [[self.fundamental_group.vertices[v] for v in path]]
            self._paths = paths
        return self._paths

    @property
    def basepoint(self):
        assert self.dim>0, "Dimension 0 vartiety has no fibration"
        if  not hasattr(self, '_basepoint'):
            if self.ctx.long_fibration and self.ctx.depth>0:
                self._basepoint=ZZ(0)
            else:
                shift = 1
                reals = [self.ctx.CF(c).real() for c in self.critical_values]
                xmin, xmax = min(reals), max(reals)
                self._basepoint = Util.simple_rational(xmin - (xmax-xmin)*shift, (xmax-xmin)/10)
        return self._basepoint

    def lift(self, v):
        v = matrix(self.extensions + self.infinity_loops).solve_left(v)
        add = [] if self.dim %2 ==1 else [0,0]
        return vector(list(v)[:-len(self.infinity_loops)] + add)
    
    def lift_modification(self, v):
        """Given a vector v, return the orthogonal projection of the homology of the modification on the homology of the hypersurface"""
        return vector(list(matrix(self.homology + self.exceptional_divisors).solve_left(v))[:len(self.homology)])
    
    @property
    def fibre_class(self):
        assert self.dim %2 ==0, "no fibre class in odd dimensions"
        return vector([0]*len(self.extensions) + [1,0])
    @property
    def hyperplane_class(self):
        assert self.dim %2 ==0, "no hyperplane class in odd dimensions"
        return matrix(self.homology).solve_left(self.fibre_class + sum(self.exceptional_divisors)) # todo in higher dimensions (>=4) we want the orthogonal projection of self.fibre_class
    @property
    def section(self):
        assert self.dim %2 ==0, "no section in odd dimensions"
        return vector([0]*len(self.extensions) + [0,1])


    # Sequential integration methods

    @classmethod
    def _derivative(self, A, P): 
        """computes the numerator of the derivative of A/P^k"""
        field = P.parent().fraction_field()
        return field(A).derivative() - A*P.derivative()         

    def integrate(self, L):
        logger.info("[%d] Computing numerical transition matrices of operator of order %d and degree %d (%d edges total)."% (self.dim, L.order(), L.degree(), len(self.fundamental_group.edges)))
        begin = time.time()

        integrator = Integrator(self.fundamental_group, L, self.ctx.nbits)
        transition_matrices = integrator.transition_matrices
        
        end = time.time()
        duration_str = time.strftime("%H:%M:%S",time.gmtime(end-begin))
        logger.info("[%d] Integration finished -- total time: %s."% (self.dim, duration_str))

        return transition_matrices

    def forget_transition_matrices(self):
        del self._integratedQ
        del self._transition_matrices
        del self._integrated_thimbles
        del self._integrated_thimblesQ

    def _compute_transition_matrices_sequential(self, rat_coefs, indices):
        R, denom = rat_coefs
        res = None
        j=0
        logger.info("[%d] Computing Picard-Fuchs equations of %d forms in dimension %d"% (self.dim, rat_coefs[0].nrows(), self.dim))
        for i, v in zip(indices, R.rows()):
            L = self.picard_fuchs_equation(v/denom)
            L = L * L.parent().gens()[0]
            integrated = self.integrate(L)
            derivatives_at_basepoint = self.derivatives_values_at_basepoint(i)
            integration_correction = diagonal_matrix([1/ZZ(factorial(k)) for k in range(L.order())])
            initial_conditions = ( integration_correction * derivatives_at_basepoint )
            if res == None:
                res = []
                for M in integrated:
                    GM = initial_conditions.submatrix(1,0).inverse() * M.submatrix(1,1) * initial_conditions.submatrix(1,0)
                    intgr = (M * initial_conditions).submatrix(0,0,1)
                    res += [block_matrix([[identity_matrix(1), intgr],[0, GM]])]
            else:
                r = L.order()-1
                intold = [M.submatrix(0,j,j,r) for M in res]
                intnew = [(M * initial_conditions).submatrix(0,0,1) for M in integrated]
                GM = [M.submatrix(j,j) for M in res]
                res = [block_matrix([[1,0, a],[0,1, b], [0,0,c]]) for a,b,c in zip(intold, intnew, GM)]
            j+=1
        return res
    
    def picard_fuchs_equation(self, v):
        denom = lcm([r.denominator() for r in v if r!=0])
        numerators = denom * v
        L = self.family.picard_fuchs_equation(numerators) * denom
        L = DifferentialOperator(L)
        return L

    def derivatives_values_at_basepoint(self, i):
        RtoS = self._RtoS()
        s=len(self.fiber.cohomology)
        w = self.cohomology[i]
        wt = self._restrict_form(w)
        derivatives = [RtoS(0), wt]
        for k in range(s-1):
            derivatives += [self._derivative(derivatives[-1], RtoS(self.P))] 
        return self.family._coordinates(derivatives, self.basepoint)

    def derivatives_coordinates(self, i):
        if not self._coordinatesQ[i]:
            s=len(self.fiber.homology)
            RtoS = self._RtoS()
            w = self.cohomology[i]
            wt = self._restrict_form(w)
            derivatives = [RtoS(0), wt]
            for k in range(s-1 if self.dim%2==0 else s-2):
                derivatives += [self._derivative(derivatives[-1], RtoS(self.P))] 
            self._coordinates[i] = self.family.coordinates(derivatives)
            self._coordinatesQ[i] = True
        return self._coordinates[i]
