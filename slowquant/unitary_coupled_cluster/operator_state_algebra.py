from collections.abc import Sequence

import numba as nb
import numpy as np
import scipy.sparse as ss

from slowquant.unitary_coupled_cluster.ci_spaces import CI_Info
from slowquant.unitary_coupled_cluster.fermionic_operator import FermionicOperator
from slowquant.unitary_coupled_cluster.operators import (
    G1,
    G2,
    G3,
    G4,
    G5,
    G6,
    G1_sa,
    G2_1_sa,
    G2_2_sa,
)
from slowquant.unitary_coupled_cluster.util import UccStructure, UpsStructure


@nb.jit(nopython=True)
def bitcount(x: int) -> int:
    """Count number of ones in binary representation of an integer.

    Implementaion of Brian Kernighan algorithm,
    https://graphics.stanford.edu/~seander/bithacks.html#CountBitsSetKernighan

    Args:
        x: Integer.

    Returns:
        Number of ones in the binary.
    """
    b = 0
    while x > 0:
        x &= x - 1
        b += 1
    return b


@nb.jit(nopython=True)
def apply_operator(
    state: np.ndarray,
    anni_idxs: np.ndarray,
    create_idxs: np.ndarray,
    num_active_orbs: int,
    parity_check: np.ndarray,
    idx2det: np.ndarray,
    det2idx: dict[int, int],
    do_unsafe: bool,
    tmp_state: np.ndarray,
    factor: float,
) -> np.ndarray:
    """Apply operator to state for a single state wave function.

    This part is outside of propagate_state for performance reasons,
    i.e., Numba JIT.

    Args:
        state: Original state.
        anni_idxs: Indicies for annihilation operators.
        create_idxs: Indicies for creation operators.
        num_active_orbs: Number of active spatial orbitals.
        parity_check: Array used to check the parity when an operator is applied.
        idx2det: Maps index to determinant.
        det2idx: Maps determinant to index.
        do_unsafe: Do unsafe.
        tmp_state: New state.
        factor: Factor in front of operator.

    Returns:
        New state.
    """
    anni_idxs = anni_idxs[::-1]
    create_idxs = create_idxs[::-1]
    # loop over all determinants in new_state
    for i, det in enumerate(idx2det):
        if abs(state[i]) < 10**-14:
            continue
        phase_changes = 0
        is_killstate = False
        # evaluate how string of annihilation operator change det
        for orb_idx in anni_idxs:
            if (det >> 2 * num_active_orbs - 1 - orb_idx) & 1 == 0:
                # If an annihilation operator works on zero, then we reach kill-state.
                is_killstate = True
                break
            det = det ^ (1 << (2 * num_active_orbs - 1 - orb_idx))
            # take care of phases using parity_check
            phase_changes += bitcount(det & parity_check[orb_idx])
        if is_killstate:
            continue
        for orb_idx in create_idxs:
            if (det >> 2 * num_active_orbs - 1 - orb_idx) & 1 == 1:
                # If creation operator works on one, then we reach kill-state.
                is_killstate = True
                break
            det = det ^ (1 << (2 * num_active_orbs - 1 - orb_idx))
            # take care of phases using parity_check
            phase_changes += bitcount(det & parity_check[orb_idx])
        if is_killstate:
            continue
        if do_unsafe:
            # For some algorithms it is guaranteed that the application of operators will always
            # keep the new determinants within a pre-defined space (in det2idx and idx2det).
            # For these algorithms it is a sign of bug if a keyerror when calling det2idx is found.
            # These algorithms thus does also not need to check for the exsistence of the new determinant
            # in det2idx.
            # For other algorithms this 'safety' is not guaranteed, hence the keyword is called 'do_unsafe'.
            if det not in det2idx:
                continue
        tmp_state[det2idx[det]] += factor * (-1) ** phase_changes * state[i]
    return tmp_state


@nb.jit(nopython=True)
def add_operator_matrix(
    op_mat: np.ndarray,
    anni_idxs: np.ndarray,
    create_idxs: np.ndarray,
    num_active_orbs: int,
    parity_check: np.ndarray,
    idx2det: np.ndarray,
    det2idx: dict[int, int],
    do_unsafe: bool,
    factor: float,
) -> np.ndarray:
    """Add matrix representation of annihilation string.

    This part is outside of propagate_state for performance reasons,
    i.e., Numba JIT.

    Args:
        op_mat: Matrix representation of operator.
        anni_idxs: Indicies for annihilation operators.
        create_idxs: Indicies for creation operators.
        num_active_orbs: Number of active spatial orbitals.
        parity_check: Array used to check the parity when an operator is applied.
        idx2det: Maps index to determinant.
        det2idx: Maps determinant to index.
        do_unsafe: Do unsafe.
        factor: Factor in front of operator.

    Returns:
        Operator matrix.
    """
    anni_idxs = anni_idxs[::-1]
    create_idxs = create_idxs[::-1]
    # loop over all determinants in new_state
    for i, det in enumerate(idx2det):
        phase_changes = 0
        is_killstate = False
        # evaluate how string of annihilation operator change det
        for orb_idx in anni_idxs:
            if (det >> 2 * num_active_orbs - 1 - orb_idx) & 1 == 0:
                # If an annihilation operator works on zero, then we reach kill-state.
                is_killstate = True
                break
            det = det ^ (1 << (2 * num_active_orbs - 1 - orb_idx))
            # take care of phases using parity_check
            phase_changes += bitcount(det & parity_check[orb_idx])
        if is_killstate:
            continue
        for orb_idx in create_idxs:
            if (det >> 2 * num_active_orbs - 1 - orb_idx) & 1 == 1:
                # If creation operator works on one, then we reach kill-state.
                is_killstate = True
                break
            det = det ^ (1 << (2 * num_active_orbs - 1 - orb_idx))
            # take care of phases using parity_check
            phase_changes += bitcount(det & parity_check[orb_idx])
        if is_killstate:
            continue
        if do_unsafe:
            # For some algorithms it is guaranteed that the application of operators will always
            # keep the new determinants within a pre-defined space (in det2idx and idx2det).
            # For these algorithms it is a sign of bug if a keyerror when calling det2idx is found.
            # These algorithms thus does also not need to check for the exsistence of the new determinant
            # in det2idx.
            # For other algorithms this 'safety' is not guaranteed, hence the keyword is called 'do_unsafe'.
            if det not in det2idx:
                continue
        op_mat[det2idx[det], i] += factor * (-1) ** phase_changes
    return op_mat


@nb.jit(nopython=True)
def apply_operator_SA(
    state: np.ndarray,
    anni_idxs: np.ndarray,
    create_idxs: np.ndarray,
    num_active_orbs: int,
    parity_check: np.ndarray,
    idx2det: np.ndarray,
    det2idx: dict[int, int],
    do_unsafe: bool,
    tmp_state: np.ndarray,
    factor: float,
) -> np.ndarray:
    """Apply operator to state for a state-averaged wave function.

    This part is outside of propagate_state for performance reasons,
    i.e., Numba JIT.

    Args:
        state: Original state.
        anni_idxs: Indicies for annihilation operators.
        create_idxs: Indicies for creation operators.
        num_active_orbs: Number of active spatial orbitals.
        parity_check: Array used to check the parity when an operator is applied.
        idx2det: Maps index to determinant.
        det2idx: Maps determinant to index.
        do_unsafe: Do unsafe.
        tmp_state: New state.
        factor: Factor in front of operator.

    Returns:
        New state.
    """
    anni_idxs = anni_idxs[::-1]
    create_idxs = create_idxs[::-1]
    # loop over all determinants in new_state
    for i, det in enumerate(idx2det):
        is_non_zero = False
        for val in state[:, i]:
            if abs(val) > 10**-14:
                is_non_zero = True
                break
        if not is_non_zero:
            continue
        phase_changes = 0
        is_killstate = False
        # evaluate how string of annihilation operator change det
        for orb_idx in anni_idxs:
            if (det >> 2 * num_active_orbs - 1 - orb_idx) & 1 == 0:
                # If an annihilation operator works on zero, then we reach kill-state.
                is_killstate = True
                break
            det = det ^ (1 << (2 * num_active_orbs - 1 - orb_idx))
            # take care of phases using parity_check
            phase_changes += bitcount(det & parity_check[orb_idx])
        if is_killstate:
            continue
        for orb_idx in create_idxs:
            if (det >> 2 * num_active_orbs - 1 - orb_idx) & 1 == 1:
                # If creation operator works on one, then we reach kill-state.
                is_killstate = True
                break
            det = det ^ (1 << (2 * num_active_orbs - 1 - orb_idx))
            # take care of phases using parity_check
            phase_changes += bitcount(det & parity_check[orb_idx])
        if is_killstate:
            continue
        if do_unsafe:
            # For some algorithms it is guaranteed that the application of operators will always
            # keep the new determinants within a pre-defined space (in det2idx and idx2det).
            # For these algorithms it is a sign of bug if a keyerror when calling det2idx is found.
            # These algorithms thus does also not need to check for the exsistence of the new determinant
            # in det2idx.
            # For other algorithms this 'safety' is not guaranteed, hence the keyword is called 'do_unsafe'.
            if det not in det2idx:
                continue
        val = factor * (-1) ** phase_changes
        tmp_state[:, det2idx[det]] += val * state[:, i]  # Update value
    return tmp_state


def build_operator_matrix(op: FermionicOperator, ci_info: CI_Info, do_unsafe: bool = False) -> np.ndarray:
    """Build matrix representation of operator.

    Args:
        op: Fermionic number and spin conserving operator.
        ci_info: Information about the CI space.
        do_unsafe: Ignore elements that are outside the space defined in ci_info. (default: False)
                If not ignored, getting elements outside the space will stop the calculation.

    Returns:
        Matrix representation of operator.
    """
    idx2det = ci_info.idx2det
    det2idx = ci_info.det2idx
    num_active_orbs = ci_info.num_active_orbs
    num_dets = len(idx2det)  # number of spin and particle conserving determinants
    op_mat = np.zeros((num_dets, num_dets))  # basis
    # Create bitstrings for parity check. Contains occupied determinant up to orbital index.
    parity_check = np.zeros(2 * num_active_orbs + 1, dtype=int)
    num = 0
    for i in range(2 * num_active_orbs - 1, -1, -1):
        num += 2**i
        parity_check[2 * num_active_orbs - i] = num
    # loop over all strings of annihilation operators in FermionicOperator sum
    for fermi_label in op.operators.keys():
        # Separate each annihilation operator string in creation and annihilation indices
        anni_idx = []
        create_idx = []
        for fermi_op in fermi_label:
            if fermi_op[1]:
                create_idx.append(fermi_op[0])
            else:
                anni_idx.append(fermi_op[0])
        anni_idx = np.array(anni_idx, dtype=np.int64)
        create_idx = np.array(create_idx, dtype=np.int64)
        op_mat = add_operator_matrix(
            op_mat,
            anni_idx,
            create_idx,
            num_active_orbs,
            parity_check,
            idx2det,
            det2idx,
            do_unsafe,
            op.operators[fermi_label],
        )
    return op_mat


def propagate_state(
    operators: list[FermionicOperator | str],
    state: np.ndarray,
    ci_info: CI_Info,
    thetas: Sequence[float],
    wf_struct: UpsStructure | UccStructure,
    do_folding: bool = True,
    do_unsafe: bool = False,
) -> np.ndarray:
    r"""Propagate state by applying operators.

    The operators will be folded to only work on the active orbitals.
    The resulting state should not be acted on with another folded operator.
    This would violate the "do not multiply folded operators" rule.

    .. math::
        \left|\tilde{0}\right> = \hat{O}\left|0\right>

    Args:
        operators: List of operators.
        state: State.
        ci_info: Information about the CI space.
        thetas: Active-space parameters.
               Ordered as (S, D, T, ...).
        wf_struct: wave function structure object.
        do_folding: Do folding of operator (default: True).
        do_unsafe: Ignore elements that are outside the space defined in ci_info. (default: False)
                If not ignored, getting elements outside the space will stop the calculation.

    Returns:
        New state.
    """
    idx2det = ci_info.idx2det
    det2idx = ci_info.det2idx
    num_inactive_orbs = ci_info.num_inactive_orbs
    num_active_orbs = ci_info.num_active_orbs
    num_virtual_orbs = ci_info.num_virtual_orbs
    if len(operators) == 0:
        return np.copy(state)
    new_state = np.copy(state)
    tmp_state = np.zeros_like(state)
    # Create bitstrings for parity check. Contains occupied determinant up to orbital index.
    parity_check = np.zeros(2 * num_active_orbs + 1, dtype=np.int64)
    num = 0
    for i in range(2 * num_active_orbs - 1, -1, -1):
        num += 2**i
        parity_check[2 * num_active_orbs - i] = num
    for op in operators[::-1]:
        # Ansatz unitary in operators
        if isinstance(op, str):
            if op not in ("U", "Ud"):
                raise ValueError(f"Unknown str operator, expected ('U', 'Ud') got {op}")
            dagger = False
            if op == "Ud":
                dagger = True
            if isinstance(wf_struct, UpsStructure):
                new_state = construct_ups_state(
                    new_state,
                    ci_info,
                    thetas,
                    wf_struct,
                    dagger=dagger,
                )
            elif isinstance(wf_struct, UccStructure):
                new_state = construct_ucc_state(
                    new_state,
                    ci_info,
                    thetas,
                    wf_struct,
                    dagger=dagger,
                )
            else:
                raise TypeError(f"Got unknown wave function structure type, {type(wf_struct)}")
        # FermionicOperator in operators
        else:
            tmp_state[:] = 0.0
            # Fold operator to only get active contributions
            if do_folding:
                op_folded = op.get_folded_operator(num_inactive_orbs, num_active_orbs, num_virtual_orbs)
            else:
                op_folded = op
            # loop over all strings of annihilation operators in FermionicOperator sum
            for fermi_label in op_folded.operators.keys():
                # Separate each annihilation operator string in creation and annihilation indices
                anni_idx = []
                create_idx = []
                for fermi_op in fermi_label:
                    if fermi_op[1]:
                        create_idx.append(fermi_op[0])
                    else:
                        anni_idx.append(fermi_op[0])
                anni_idx = np.array(anni_idx, dtype=np.int64)
                create_idx = np.array(create_idx, dtype=np.int64)
                tmp_state = apply_operator(
                    new_state,
                    anni_idx,
                    create_idx,
                    num_active_orbs,
                    parity_check,
                    idx2det,
                    det2idx,
                    do_unsafe,
                    tmp_state,
                    op_folded.operators[fermi_label],
                )
            new_state = np.copy(tmp_state)
    return new_state


def propagate_state_SA(
    operators: list[FermionicOperator | str],
    state: np.ndarray,
    ci_info: CI_Info,
    thetas: Sequence[float],
    wf_struct: UpsStructure,
    do_folding: bool = True,
    do_unsafe: bool = False,
) -> np.ndarray:
    r"""Propagate state by applying operator.

    The operator will be folded to only work on the active orbitals.
    The resulting state should not be acted on with another folded operator.
    This would violate the "do not multiply folded operators" rule.

    .. math::
        \left|\tilde{0}\right> = \hat{O}\left|0\right>

    Args:
        operators: List of operators.
        state: State.
        ci_info: Information about the CI space.
        thetas: Active-space parameters.
               Ordered as (S, D, T, ...).
        wf_struct: wave function structure object.
        do_folding: Do folding of operator (default: True).
        do_unsafe: Ignore elements that are outside the space defined in ci_info. (default: False)
                If not ignored, getting elements outside the space will stop the calculation.

    Returns:
        New state.
    """
    idx2det = ci_info.idx2det
    det2idx = ci_info.det2idx
    num_inactive_orbs = ci_info.num_inactive_orbs
    num_active_orbs = ci_info.num_active_orbs
    num_virtual_orbs = ci_info.num_virtual_orbs
    if len(operators) == 0:
        return np.copy(state)
    new_state = np.copy(state)
    tmp_state = np.zeros_like(state)
    # Create bitstrings for parity check. Contains occupied determinant up to orbital index.
    parity_check = np.zeros(2 * num_active_orbs + 1, dtype=int)
    num = 0
    for i in range(2 * num_active_orbs - 1, -1, -1):
        num += 2**i
        parity_check[2 * num_active_orbs - i] = num
    for op in operators[::-1]:
        # Ansatz unitary in operators
        if isinstance(op, str):
            if op not in ("U", "Ud"):
                raise ValueError(f"Unknown str operator, expected ('U', 'Ud') got {op}")
            dagger = False
            if op == "Ud":
                dagger = True
            if isinstance(wf_struct, UpsStructure):
                new_state = construct_ups_state_SA(
                    new_state,
                    ci_info,
                    thetas,
                    wf_struct,
                    dagger=dagger,
                )
            else:
                raise TypeError(f"Got unknown wave function structure type, {type(wf_struct)}")
        # FermionicOperator in operators
        else:
            tmp_state[:] = 0.0
            # Fold operator to only get active contributions
            if do_folding:
                op_folded = op.get_folded_operator(num_inactive_orbs, num_active_orbs, num_virtual_orbs)
            else:
                op_folded = op
            # loop over all strings of annihilation operators in FermionicOperator sum
            for fermi_label in op_folded.operators.keys():
                # Separate each annihilation operator string in creation and annihilation indices
                anni_idx = []
                create_idx = []
                for fermi_op in fermi_label:
                    if fermi_op[1]:
                        create_idx.append(fermi_op[0])
                    else:
                        anni_idx.append(fermi_op[0])
                anni_idx = np.array(anni_idx, dtype=np.int64)
                create_idx = np.array(create_idx, dtype=np.int64)
                tmp_state = apply_operator_SA(
                    new_state,
                    anni_idx,
                    create_idx,
                    num_active_orbs,
                    parity_check,
                    idx2det,
                    det2idx,
                    do_unsafe,
                    tmp_state,
                    op_folded.operators[fermi_label],
                )
            new_state = np.copy(tmp_state)
    return new_state


def expectation_value(
    bra: np.ndarray,
    operators: list[FermionicOperator | str],
    ket: np.ndarray,
    ci_info: CI_Info,
    thetas: Sequence[float],
    wf_struct: UpsStructure | UccStructure,
    do_folding: bool = True,
    do_unsafe: bool = False,
) -> float:
    """Calculate expectation value of operator using propagate state.

    Args:
        bra: Bra state.
        operators: Operator.
        ket: Ket state.
        ci_info: Information about the CI space.
        thetas: Active-space parameters.
               Ordered as (S, D, T, ...).
        wf_struct: Wave function structure object.
        do_folding: Do folding of operator (default: True).
        do_unsafe: Ignore elements that are outside the space defined in ci_info. (default: False)
                If not ignored, getting elements outside the space will stop the calculation.

    Returns:
        Expectation value.
    """
    # build state vector of operator on ket
    op_ket = propagate_state(
        operators,
        ket,
        ci_info,
        thetas,
        wf_struct,
        do_folding=do_folding,
        do_unsafe=do_unsafe,
    )
    val = bra @ op_ket
    if not isinstance(val, float):
        raise ValueError(f"Calculated expectation value is not a float, got type {type(val)}")
    return val


def expectation_value_SA(
    bra: np.ndarray,
    operators: list[FermionicOperator | str],
    ket: np.ndarray,
    ci_info: CI_Info,
    thetas: Sequence[float],
    wf_struct: UpsStructure,
    do_folding: bool = True,
) -> float:
    """Calculate expectation value of operator with a SA wave function using propagate state.

    Args:
        bra: Bra state.
        operators: Operator.
        ket: Ket state.
        ci_info: Information about the CI space.
        thetas: Active-space parameters.
               Ordered as (S, D, T, ...).
        wf_struct: Wave function structure object.
        do_folding: Do folding of operator (default: True).

    Returns:
        Expectation value.
    """
    # build state vector of operator on ket
    op_ket = propagate_state_SA(
        operators,
        ket,
        ci_info,
        thetas,
        wf_struct,
        do_folding=do_folding,
    )
    val = np.einsum("ij,ij->", bra, op_ket)
    if not isinstance(val, float):
        raise ValueError(f"Calculated expectation value is not a float, got type {type(val)}")
    return val / len(bra)


def construct_ucc_state(
    state: np.ndarray,
    ci_info: CI_Info,
    thetas: Sequence[float],
    ucc_struct: UccStructure,
    dagger: bool = False,
) -> np.ndarray:
    """Construct UCC state by applying UCC unitary to reference state.

    Args:
        state: Reference state vector.
        ci_info: Information about the CI space.
        thetas: Active-space parameters.
               Ordered as (S, D, T, ...).
        ucc_struct: UCCStructure object.
        dagger: If true, do dagger unitaries.

    Returns:
        New state vector with unitaries applied.
    """
    # Build up T matrix based on excitations in ucc_struct and given thetas
    T = get_ucc_T(thetas, ucc_struct, ci_info.space_extension_offset)
    # Evil matrix construction
    Tmat = build_operator_matrix(T, ci_info)
    if dagger:
        return ss.linalg.expm_multiply(-Tmat, state, traceA=0.0)
    return ss.linalg.expm_multiply(Tmat, state, traceA=0.0)


def get_ucc_T(
    thetas: Sequence[float],
    ucc_struct: UccStructure,
    offset: int = 0,
) -> FermionicOperator:
    """Construct UCC operator.

    Args:
        thetas: Active-space parameters.
               Ordered as (S, D, T, ...).
        ucc_struct: UCCStructure object.
        offset: Offset needed for extended spaces.

    Returns:
        UCC operator.
    """
    # Build up T matrix based on excitations in ucc_struct and given thetas
    T = FermionicOperator({})
    for exc_type, exc_indices, theta in zip(
        ucc_struct.excitation_operator_type, ucc_struct.excitation_indices, thetas
    ):
        if abs(theta) < 10**-14:
            continue
        if exc_type == "sa_single":
            (i, a) = np.array(exc_indices) + offset
            T += theta * G1_sa(i, a, True)
        elif exc_type == "sa_double_1":
            (i, j, a, b) = np.array(exc_indices) + offset
            T += theta * G2_1_sa(i, j, a, b, True)
        elif exc_type == "sa_double_2":
            (i, j, a, b) = np.array(exc_indices) + offset
            T += theta * G2_2_sa(i, j, a, b, True)
        elif exc_type == "single":
            (i, a) = np.array(exc_indices) + 2 * offset
            T += theta * G1(i, a, True)
        elif exc_type == "double":
            (i, j, a, b) = np.array(exc_indices) + 2 * offset
            T += theta * G2(i, j, a, b, True)
        elif exc_type == "triple":
            (i, j, k, a, b, c) = np.array(exc_indices) + 2 * offset
            T += theta * G3(i, j, k, a, b, c, True)
        elif exc_type == "quadruple":
            (i, j, k, l, a, b, c, d) = np.array(exc_indices) + 2 * offset
            T += theta * G4(i, j, k, l, a, b, c, d, True)
        elif exc_type == "quintuple":
            (i, j, k, l, m, a, b, c, d, e) = np.array(exc_indices) + 2 * offset
            T += theta * G5(i, j, k, l, m, a, b, c, d, e, True)
        elif exc_type == "sextuple":
            (i, j, k, l, m, n, a, b, c, d, e, f) = np.array(exc_indices) + 2 * offset
            T += theta * G6(i, j, k, l, m, n, a, b, c, d, e, f, True)
        else:
            raise ValueError(f"Got unknown excitation type, {exc_type}")
    return T


def construct_ups_state(
    state: np.ndarray,
    ci_info: CI_Info,
    thetas: Sequence[float],
    ups_struct: UpsStructure,
    dagger: bool = False,
) -> np.ndarray:
    r"""Construct unitary product state by applying UPS unitary to reference state.

    .. math::
        \boldsymbol{U}_N...\boldsymbol{U}_0\left|\nu\right> = \left|\tilde\nu\right>

    #. 10.48550/arXiv.2303.10825, Eq. 15

    Args:
        state: Reference state vector.
        ci_info: Information about the CI space.
        thetas: Ansatz parameters values.
        ups_struct: Unitary product state structure.
        dagger: If true, do dagger unitaries.

    Returns:
        New state vector with unitaries applied.
    """
    tmp = state.copy()
    order = 1
    offset = ci_info.space_extension_offset
    if dagger:
        order = -1
    # Loop over all excitation in UPSStructure
    for exc_type, exc_indices, theta in zip(
        ups_struct.excitation_operator_type[::order], ups_struct.excitation_indices[::order], thetas[::order]
    ):
        if abs(theta) < 10**-14:
            continue
        if dagger:
            theta = -theta
        if exc_type in ("sa_single",):
            A = 1  # 2**(-1/2)
            (i, a) = np.array(exc_indices) + offset
            # Create T matrices
            Ta = G1(i * 2, a * 2, True)
            Tb = G1(i * 2 + 1, a * 2 + 1, True)
            # Analytical application on state vector
            tmp = (
                tmp
                + np.sin(A * theta)
                * propagate_state(
                    [Ta],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
                + (1 - np.cos(A * theta))
                * propagate_state(
                    [Ta, Ta],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
            )
            tmp = (
                tmp
                + np.sin(A * theta)
                * propagate_state(
                    [Tb],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
                + (1 - np.cos(A * theta))
                * propagate_state(
                    [Tb, Tb],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
            )
        elif exc_type in ("single", "double"):
            # Create T matrix
            if exc_type == "single":
                (i, a) = np.array(exc_indices) + 2 * offset
                T = G1(i, a, True)
            elif exc_type == "double":
                (i, j, a, b) = np.array(exc_indices) + 2 * offset
                T = G2(i, j, a, b, True)
            else:
                raise ValueError(f"Got unknown excitation type: {exc_type}")
            # Analytical application on state vector
            tmp = (
                tmp
                + np.sin(theta)
                * propagate_state(
                    [T],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
                + (1 - np.cos(theta))
                * propagate_state(
                    [T, T],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
            )
        else:
            raise ValueError(f"Got unknown excitation type, {exc_type}")
    return tmp


def construct_ups_state_SA(
    state: np.ndarray,
    ci_info: CI_Info,
    thetas: Sequence[float],
    ups_struct: UpsStructure,
    dagger: bool = False,
) -> np.ndarray:
    r"""Construct unitary product state by applying UPS unitary to reference state.

    .. math::
        \boldsymbol{U}_N...\boldsymbol{U}_0\left|\nu\right> = \left|\tilde\nu\right>

    #. 10.48550/arXiv.2303.10825, Eq. 15

    Args:
        state: Reference state vector.
        ci_info: Information about the CI space.
        thetas: Ansatz parameters values.
        ups_struct: Unitary product state structure.
        dagger: If true, do dagger unitaries.

    Returns:
        New state vector with unitaries applied.
    """
    tmp = state.copy()
    order = 1
    offset = ci_info.space_extension_offset
    if dagger:
        order = -1
    # Loop over all excitation in UPSStructure
    for exc_type, exc_indices, theta in zip(
        ups_struct.excitation_operator_type[::order], ups_struct.excitation_indices[::order], thetas[::order]
    ):
        if abs(theta) < 10**-14:
            continue
        if dagger:
            theta = -theta
        if exc_type in ("sa_single",):
            A = 1  # 2**(-1/2)
            (i, a) = np.array(exc_indices) + offset
            # Create T matrices
            Ta = G1(i * 2, a * 2, True)
            Tb = G1(i * 2 + 1, a * 2 + 1, True)
            # Analytical application on state vector
            tmp = (
                tmp
                + np.sin(A * theta)
                * propagate_state_SA(
                    [Ta],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
                + (1 - np.cos(A * theta))
                * propagate_state_SA(
                    [Ta, Ta],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
            )
            tmp = (
                tmp
                + np.sin(A * theta)
                * propagate_state_SA(
                    [Tb],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
                + (1 - np.cos(A * theta))
                * propagate_state_SA(
                    [Tb, Tb],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
            )
        elif exc_type in ("single", "double"):
            # Create T matrix
            if exc_type == "single":
                (i, a) = np.array(exc_indices) + 2 * offset
                T = G1(i, a, True)
            elif exc_type == "double":
                (i, j, a, b) = np.array(exc_indices) + 2 * offset
                T = G2(i, j, a, b, True)
            else:
                raise ValueError(f"Got unknown excitation type: {exc_type}")
            # Analytical application on state vector
            tmp = (
                tmp
                + np.sin(theta)
                * propagate_state_SA(
                    [T],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
                + (1 - np.cos(theta))
                * propagate_state_SA(
                    [T, T],
                    tmp,
                    ci_info,
                    thetas,
                    ups_struct,
                    do_folding=False,
                )
            )
        else:
            raise ValueError(f"Got unknown excitation type, {exc_type}")
    return tmp


def propagate_unitary(
    state: np.ndarray,
    idx: int,
    ci_info: CI_Info,
    thetas: Sequence[float],
    ups_struct: UpsStructure,
) -> np.ndarray:
    """Apply unitary from UPS operator number 'idx' to state.

    Args:
        state: State vector.
        idx: Index of operator in the ups_struct.
        ci_info: Information about the CI space.
        thetas: Values for ansatz parameters.
        ups_struct: UPS structure object.

    Returns:
        State with unitary applied.
    """
    # Select unitary operation based on idx
    exc_type = ups_struct.excitation_operator_type[idx]
    exc_indices = ups_struct.excitation_indices[idx]
    theta = thetas[idx]
    offset = ci_info.space_extension_offset
    if abs(theta) < 10**-14:
        return np.copy(state)
    if exc_type in ("sa_single",):
        A = 1  # 2**(-1/2)
        (i, a) = np.array(exc_indices) + offset
        # Create T matrix
        Ta = G1(i * 2, a * 2, True)
        Tb = G1(i * 2 + 1, a * 2 + 1, True)
        # Analytical application on state vector
        tmp = (
            state
            + np.sin(A * theta)
            * propagate_state(
                [Ta],
                state,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
            + (1 - np.cos(A * theta))
            * propagate_state(
                [Ta, Ta],
                state,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
        )
        tmp = (
            tmp
            + np.sin(A * theta)
            * propagate_state(
                [Tb],
                tmp,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
            + (1 - np.cos(A * theta))
            * propagate_state(
                [Tb, Tb],
                tmp,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
        )
    elif exc_type in ("single", "double"):
        # Create T matrix
        if exc_type == "single":
            (i, a) = np.array(exc_indices) + 2 * offset
            T = G1(i, a, True)
        elif exc_type == "double":
            (i, j, a, b) = np.array(exc_indices) + 2 * offset
            T = G2(i, j, a, b, True)
        else:
            raise ValueError(f"Got unknown excitation type: {exc_type}")
        # Analytical application on state vector
        tmp = (
            state
            + np.sin(theta)
            * propagate_state(
                [T],
                state,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
            + (1 - np.cos(theta))
            * propagate_state(
                [T, T],
                state,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
        )
    else:
        raise ValueError(f"Got unknown excitation type, {exc_type}")
    return tmp


def propagate_unitary_SA(
    state: np.ndarray,
    idx: int,
    ci_info: CI_Info,
    thetas: Sequence[float],
    ups_struct: UpsStructure,
) -> np.ndarray:
    """Apply unitary from UPS operator number 'idx' to state.

    Args:
        state: State vector.
        idx: Index of operator in the ups_struct.
        ci_info: Information about the CI space.
        thetas: Values for ansatz parameters.
        ups_struct: UPS structure object.

    Returns:
        State with unitary applied.
    """
    # Select unitary operation based on idx
    exc_type = ups_struct.excitation_operator_type[idx]
    exc_indices = ups_struct.excitation_indices[idx]
    theta = thetas[idx]
    offset = ci_info.space_extension_offset
    if abs(theta) < 10**-14:
        return np.copy(state)
    if exc_type in ("sa_single",):
        A = 1  # 2**(-1/2)
        (i, a) = np.array(exc_indices) + offset
        # Create T matrix
        Ta = G1(i * 2, a * 2, True)
        Tb = G1(i * 2 + 1, a * 2 + 1, True)
        # Analytical application on state vector
        tmp = (
            state
            + np.sin(A * theta)
            * propagate_state_SA(
                [Ta],
                state,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
            + (1 - np.cos(A * theta))
            * propagate_state_SA(
                [Ta, Ta],
                state,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
        )
        tmp = (
            tmp
            + np.sin(A * theta)
            * propagate_state_SA(
                [Tb],
                tmp,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
            + (1 - np.cos(A * theta))
            * propagate_state_SA(
                [Tb, Tb],
                tmp,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
        )
    elif exc_type in ("single", "double"):
        # Create T matrix
        if exc_type == "single":
            (i, a) = np.array(exc_indices) + 2 * offset
            T = G1(i, a, True)
        elif exc_type == "double":
            (i, j, a, b) = np.array(exc_indices) + 2 * offset
            T = G2(i, j, a, b, True)
        else:
            raise ValueError(f"Got unknown excitation type: {exc_type}")
        # Analytical application on state vector
        tmp = (
            state
            + np.sin(theta)
            * propagate_state_SA(
                [T],
                state,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
            + (1 - np.cos(theta))
            * propagate_state_SA(
                [T, T],
                state,
                ci_info,
                thetas,
                ups_struct,
                do_folding=False,
            )
        )
    else:
        raise ValueError(f"Got unknown excitation type, {exc_type}")
    return tmp


def get_grad_action(
    state: np.ndarray,
    idx: int,
    ci_info: CI_Info,
    ups_struct: UpsStructure,
) -> np.ndarray:
    r"""Get effect of differentiation with respect to "idx" operator in the UPS expansion.

    .. math::
        \frac{\partial}{\partial \theta_i}\left(\left<\text{CSF}\right|\boldsymbol{U}(\theta_{i-1})\boldsymbol{U}(\theta_i)\right) =
        \left<\text{CSF}\right|\boldsymbol{U}(\theta_{i-1})\frac{\partial \boldsymbol{U}(\theta_i)}{\partial \theta_i}

    With,

    .. math::
        \begin{align}
        \frac{\partial \boldsymbol{U}(\theta_i)}{\partial \theta_i} &= \frac{\partial}{\partial \theta_i}\exp\left(\theta_i \hat{T}_i\right)\\
                &= \exp\left(\theta_i \hat{T}_i\right)\hat{T}_i
        \end{align}

    This function only applies the $\hat{T}_i$ part to the state.

    #. 10.48550/arXiv.2303.10825, Eq. 20 (appendix - v1)

    Args:
        state: State vector.
        idx: Index of operator in the ups_struct.
        ci_info: Information about the CI space.
        ups_struct: UPS structure object.

    Returns:
        State with derivative of the idx'th unitary applied.
    """
    # Select unitary operation based on idx
    exc_type = ups_struct.excitation_operator_type[idx]
    exc_indices = ups_struct.excitation_indices[idx]
    offset = ci_info.space_extension_offset
    if exc_type in ("sa_single",):
        # Create T matrix
        A = 1  # 2**(-1/2)
        (i, a) = np.array(exc_indices) + offset
        Ta = G1(i * 2, a * 2, True)
        Tb = G1(i * 2 + 1, a * 2 + 1, True)
        # Apply missing T factor of derivative
        tmp = propagate_state(
            [A * (Ta + Tb)],
            state,
            ci_info,
            (0.0,),
            ups_struct,
            do_folding=False,
        )
    elif exc_type in ("single", "double"):
        # Create T matrix
        if exc_type == "single":
            (i, a) = np.array(exc_indices) + 2 * offset
            T = G1(i, a, True)
        elif exc_type == "double":
            (i, j, a, b) = np.array(exc_indices) + 2 * offset
            T = G2(i, j, a, b, True)
        else:
            raise ValueError(f"Got unknown excitation type: {exc_type}")
        # Apply missing T factor of derivative
        tmp = propagate_state(
            [T],
            state,
            ci_info,
            (0.0,),
            ups_struct,
            do_folding=False,
        )
    else:
        raise ValueError(f"Got unknown excitation type, {exc_type}")
    return tmp


def get_grad_action_SA(
    state: np.ndarray,
    idx: int,
    ci_info: CI_Info,
    ups_struct: UpsStructure,
) -> np.ndarray:
    r"""Get effect of differentiation with respect to "idx" operator in the UPS expansion.

    .. math::
        \frac{\partial}{\partial \theta_i}\left(\left<\text{CSF}\right|\boldsymbol{U}(\theta_{i-1})\boldsymbol{U}(\theta_i)\right) =
        \left<\text{CSF}\right|\boldsymbol{U}(\theta_{i-1})\frac{\partial \boldsymbol{U}(\theta_i)}{\partial \theta_i}

    With,

    .. math::
        \begin{align}
        \frac{\partial \boldsymbol{U}(\theta_i)}{\partial \theta_i} &= \frac{\partial}{\partial \theta_i}\exp\left(\theta_i \hat{T}_i\right)\\
                &= \exp\left(\theta_i \hat{T}_i\right)\hat{T}_i
        \end{align}

    This function only applies the $\hat{T}_i$ part to the state.

    #. 10.48550/arXiv.2303.10825, Eq. 20 (appendix - v1)

    Args:
        state: State vector.
        idx: Index of operator in the ups_struct.
        ci_info: Information about the CI space.
        ups_struct: UPS structure object.

    Returns:
        State with derivative of the idx'th unitary applied.
    """
    # Select unitary operation based on idx
    exc_type = ups_struct.excitation_operator_type[idx]
    exc_indices = ups_struct.excitation_indices[idx]
    offset = ci_info.space_extension_offset
    if exc_type in ("sa_single",):
        # Create T matrix
        A = 1  # 2**(-1/2)
        (i, a) = np.array(exc_indices) + offset
        Ta = G1(i * 2, a * 2, True)
        Tb = G1(i * 2 + 1, a * 2 + 1, True)
        # Apply missing T factor of derivative
        tmp = propagate_state_SA(
            [A * (Ta + Tb)],
            state,
            ci_info,
            (0.0,),
            ups_struct,
            do_folding=False,
        )
    elif exc_type in ("single", "double"):
        # Create T matrix
        if exc_type == "single":
            (i, a) = np.array(exc_indices) + 2 * offset
            T = G1(i, a, True)
        elif exc_type == "double":
            (i, j, a, b) = np.array(exc_indices) + 2 * offset
            T = G2(i, j, a, b, True)
        else:
            raise ValueError(f"Got unknown excitation type: {exc_type}")
        # Apply missing T factor of derivative
        tmp = propagate_state_SA(
            [T],
            state,
            ci_info,
            (0.0,),
            ups_struct,
            do_folding=False,
        )
    else:
        raise ValueError(f"Got unknown excitation type, {exc_type}")
    return tmp
