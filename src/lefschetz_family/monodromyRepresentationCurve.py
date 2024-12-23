# -*- coding: utf-8 -*-

import sage.all

from .numperiods.familyNew import Family
from .numperiods.cohomology import Cohomology
from ore_algebra import *

from sage.modules.free_module_element import vector
from sage.rings.polynomial.polynomial_ring_constructor import PolynomialRing
from sage.rings.qqbar import QQbar
from sage.matrix.constructor import matrix
from sage.arith.misc import gcd
from sage.rings.integer_ring import ZZ
from sage.matrix.special import identity_matrix
from sage.matrix.special import diagonal_matrix
from sage.matrix.special import block_matrix
from sage.matrix.special import block_diagonal_matrix
from sage.matrix.special import zero_matrix
from sage.arith.functions import lcm
from sage.misc.misc_c import prod
from sage.misc.flatten import flatten

from sage.misc.prandom import randint

from .util import Util
from .context import Context
from .exceptionalDivisorComputer import ExceptionalDivisorComputer
from .monodromyRepresentation import MonodromyRepresentation


import logging
import time

logger = logging.getLogger(__name__)


class MonodromyRepresentationCurve(MonodromyRepresentation):
    
    @property
    def monodromy_matrices_desingularisation(self):
        if not hasattr(self, '_monodromy_matrices_desingularisation'):
            monodromy_matrices_desingularisation = []
            for M in self.monodromy_matrices:
                decomposition = self.monodromy_class(M)
                assert prod(list(reversed(decomposition))) == M
                monodromy_matrices_desingularisation += [decomposition]

            self._monodromy_matrices_desingularisation = monodromy_matrices_desingularisation

        return self._monodromy_matrices_desingularisation

    def monodromy_class(self, M):
        if M==1:
            return []
        if (M-1).rank() != 1:
            raise Exception("Unknown singular fibre type")
        v = (M-1).image().gen(0)
        n = gcd(v)
        decomposition = [(M-1)/n + 1] * n
        decomposition = [M.change_ring(ZZ) for M in decomposition]
        return decomposition
    
    @property
    def add(self):
        if not hasattr(self, '_add'):
            self._add = 0
        return self._add