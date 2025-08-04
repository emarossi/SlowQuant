import numba as nb
import numpy as np


@nb.jit(nopython=True)
def RDM1(p: int, q: int, num_inactive_orbs: int, num_active_orbs: int, rdm1: np.ndarray) -> float:
    r"""Get full space one-electron reduced density matrix element.

    The only non-zero elements are:

    .. math::
        \Gamma^{[1]}_{pq} = \left\{\begin{array}{ll}
                            2\delta_{ij} & pq = ij\\
                            \left<0\left|\hat{E}_{vw}\right|0\right> & pq = vw\\
                            0 & \text{otherwise} \\
                            \end{array} \right.

    and the symmetry `\Gamma^{[1]}_{pq}=\Gamma^{[1]}_{qp}`:math:.

    Args:
        p: Spatial orbital index.
        q: Spatial orbital index.
        num_inactive_orbs: Number of spatial inactive orbitals.
        num_active_orbs: Number of spatial active orbitals.
        rdm1: Active part of 1-RDM.

    Returns:
        One-electron reduced density matrix element.
    """
    virt_start = num_inactive_orbs + num_active_orbs
    if p >= virt_start or q >= virt_start:
        # Zero if any virtual index
        return 0
    elif p >= num_inactive_orbs and q >= num_inactive_orbs:
        # All active index
        return rdm1[p - num_inactive_orbs, q - num_inactive_orbs]
    elif p < num_inactive_orbs and q < num_inactive_orbs:
        # All inactive indx
        if p == q:
            return 2
        return 0
    # One inactive and one active index
    return 0


@nb.jit(nopython=True)
def RDM2(
    p: int,
    q: int,
    r: int,
    s: int,
    num_inactive_orbs: int,
    num_active_orbs: int,
    rdm1: np.ndarray,
    rdm2: np.ndarray,
) -> float:
    r"""Get full space two-electron reduced density matrix element.

    .. math::
        \Gamma^{[2]}_{pqrs} = \left\{\begin{array}{ll}
                              4\delta_{ij}\delta_{kl} - 2\delta_{jk}\delta_{il} & pqrs = ijkl\\
                              2\delta_{ij} \Gamma^{[1]}_{vw} & pqrs = vwij\\
                              - \delta_{ij}\Gamma^{[1]}_{vw} & pqrs = ivwj\\
                              \left<0\left|\hat{e}_{vwxy}\right|0\right> & pqrs = vwxy\\
                              0 & \text{otherwise} \\
                              \end{array} \right.

    and the symmetry `\Gamma^{[2]}_{pqrs}=\Gamma^{[2]}_{rspq}=\Gamma^{[2]}_{qpsr}=\Gamma^{[2]}_{srqp}`:math:.

    Args:
        p: Spatial orbital index.
        q: Spatial orbital index.
        r: Spatial orbital index.
        s: Spatial orbital index.
        num_inactive_orbs: Number of spatial inactive orbitals.
        num_active_orbs: Number of spatial active orbitals.
        rdm1: Active part of 1-RDM.
        rdm2: Active part of 2-RDM.

    Returns:
        Two-electron reduced density matrix element.
    """
    virt_start = num_inactive_orbs + num_active_orbs
    if p >= virt_start or q >= virt_start or r >= virt_start or s >= virt_start:
        # Zero if any virtual index
        return 0
    elif (
        p >= num_inactive_orbs
        and q >= num_inactive_orbs
        and r >= num_inactive_orbs
        and s >= num_inactive_orbs
    ):
        return rdm2[
            p - num_inactive_orbs,
            q - num_inactive_orbs,
            r - num_inactive_orbs,
            s - num_inactive_orbs,
        ]
    elif (
        p < num_inactive_orbs and q >= num_inactive_orbs and r >= num_inactive_orbs and s < num_inactive_orbs
    ):
        # iuvj type index
        if p == s:
            return -rdm1[q - num_inactive_orbs, r - num_inactive_orbs]
        return 0
    elif (
        p >= num_inactive_orbs and q < num_inactive_orbs and r < num_inactive_orbs and s >= num_inactive_orbs
    ):
        # uijv type index
        if q == r:
            return -rdm1[p - num_inactive_orbs, s - num_inactive_orbs]
        return 0
    elif (
        p >= num_inactive_orbs and q >= num_inactive_orbs and r < num_inactive_orbs and s < num_inactive_orbs
    ):
        # uvij type index
        if r == s:
            return 2 * rdm1[p - num_inactive_orbs, q - num_inactive_orbs]
        return 0
    elif (
        p < num_inactive_orbs and q < num_inactive_orbs and r >= num_inactive_orbs and s >= num_inactive_orbs
    ):
        # ijuv type index
        if p == q:
            return 2 * rdm1[r - num_inactive_orbs, s - num_inactive_orbs]
        return 0
    elif p < num_inactive_orbs and q < num_inactive_orbs and r < num_inactive_orbs and s < num_inactive_orbs:
        # All inactive index
        val = 0
        if p == q and r == s:
            val += 4
        if q == r and p == s:
            val -= 2
        return val
    # Everything else
    return 0


@nb.jit(nopython=True)
def get_electronic_energy(
    h_int: np.ndarray,
    g_int: np.ndarray,
    num_inactive_orbs: int,
    num_active_orbs: int,
    rdm1: np.ndarray,
    rdm2: np.ndarray,
) -> float:
    r"""Calculate electronic energy.

    .. math::
        E = \sum_{pq}h_{pq}\Gamma^{[1]}_{pq} + \frac{1}{2}\sum_{pqrs}g_{pqrs}\Gamma^{[2]}_{pqrs}

    Args:
        h_int: One-electron integrals in MO.
        g_int: Two-electron integrals in MO.
        num_inactive_orbs: Number of inactive orbitals.
        num_active_orbs: Number of active orbitals.
        rdm1: Active part of 1-RDM.
        rdm2: Active part of 2-RDM.

    Returns:
        Electronic energy.
    """
    energy = 0
    for p in range(num_inactive_orbs + num_active_orbs):
        for q in range(num_inactive_orbs + num_active_orbs):
            energy += h_int[p, q] * RDM1(p, q, num_inactive_orbs, num_active_orbs, rdm1)
    for p in range(num_inactive_orbs + num_active_orbs):
        for q in range(num_inactive_orbs + num_active_orbs):
            for r in range(num_inactive_orbs + num_active_orbs):
                for s in range(num_inactive_orbs + num_active_orbs):
                    energy += (
                        1
                        / 2
                        * g_int[p, q, r, s]
                        * RDM2(p, q, r, s, num_inactive_orbs, num_active_orbs, rdm1, rdm2)
                    )
    return energy


@nb.jit(nopython=True)
def get_orbital_gradient(
    h_int: np.ndarray,
    g_int: np.ndarray,
    kappa_idx: list[tuple[int, int]],
    num_inactive_orbs: int,
    num_active_orbs: int,
    rdm1: np.ndarray,
    rdm2: np.ndarray,
) -> np.ndarray:
    r"""Calculate the orbital gradient.

    .. math::
        g_{pq}^{\hat{\kappa}} = \left<0\left|\left[\hat{\kappa}_{pq},\hat{H}\right]\right|0\right>

    Args:
        h_int: One-electron integrals in MO in Hamiltonian.
        g_int: Two-electron integrals in MO in Hamiltonian.
        kappa_idx: Orbital parameter indices in spatial basis.
        num_inactive_orbs: Number of inactive orbitals in spatial basis.
        num_active_orbs: Number of active orbitals in spatial basis.
        rdm1: Active part of 1-RDM.
        rdm2: Active part of 2-RDM.

    Returns:
        Orbital gradient.
    """
    gradient = np.zeros(len(kappa_idx))
    for idx, (m, n) in enumerate(kappa_idx):
        # 1e contribution
        for p in range(num_inactive_orbs + num_active_orbs):
            gradient[idx] += 2 * h_int[n, p] * RDM1(m, p, num_inactive_orbs, num_active_orbs, rdm1)
            gradient[idx] -= 2 * h_int[p, m] * RDM1(p, n, num_inactive_orbs, num_active_orbs, rdm1)
        # 2e contribution
        for p in range(num_inactive_orbs + num_active_orbs):
            for q in range(num_inactive_orbs + num_active_orbs):
                for r in range(num_inactive_orbs + num_active_orbs):
                    gradient[idx] += g_int[n, p, q, r] * RDM2(
                        m, p, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    gradient[idx] -= g_int[p, m, q, r] * RDM2(
                        p, n, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    gradient[idx] -= g_int[m, p, q, r] * RDM2(
                        n, p, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    gradient[idx] += g_int[p, n, q, r] * RDM2(
                        p, m, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
    return gradient


@nb.jit(nopython=True)
def get_orbital_gradient_response(
    h_int: np.ndarray,
    g_int: np.ndarray,
    kappa_idx: list[tuple[int, int]],
    num_inactive_orbs: int,
    num_active_orbs: int,
    rdm1: np.ndarray,
    rdm2: np.ndarray,
) -> np.ndarray:
    r"""Calculate the response orbital parameter gradient.

    .. math::
        g_{pq}^{\hat{q}} = \left<0\left|\left[\hat{q}_{pq},\hat{H}\right]\right|0\right>

    Args:
        h_int: One-electron integrals in MO in Hamiltonian.
        g_int: Two-electron integrals in MO in Hamiltonian.
        kappa_idx: Orbital parameter indices in spatial basis.
        num_inactive_orbs: Number of inactive orbitals in spatial basis.
        num_active_orbs: Number of active orbitals in spatial basis.
        rdm1: Active part of 1-RDM.
        rdm2: Active part of 2-RDM.

    Returns:
        Orbital response parameter gradient.
    """
    gradient = np.zeros(2 * len(kappa_idx))
    for idx, (m, n) in enumerate(kappa_idx):
        # 1e contribution
        for p in range(num_inactive_orbs + num_active_orbs):
            gradient[idx] += h_int[n, p] * RDM1(m, p, num_inactive_orbs, num_active_orbs, rdm1)
            gradient[idx] -= h_int[p, m] * RDM1(p, n, num_inactive_orbs, num_active_orbs, rdm1)
        # 2e contribution
        for p in range(num_inactive_orbs + num_active_orbs):
            for q in range(num_inactive_orbs + num_active_orbs):
                for r in range(num_inactive_orbs + num_active_orbs):
                    gradient[idx] += (
                        1
                        / 2
                        * g_int[n, p, q, r]
                        * RDM2(m, p, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2)
                    )
                    gradient[idx] -= (
                        1
                        / 2
                        * g_int[p, m, q, r]
                        * RDM2(p, n, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2)
                    )
                    gradient[idx] -= (
                        1
                        / 2
                        * g_int[m, p, q, r]
                        * RDM2(n, p, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2)
                    )
                    gradient[idx] += (
                        1
                        / 2
                        * g_int[p, n, q, r]
                        * RDM2(p, m, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2)
                    )
    shift = len(kappa_idx)
    for idx, (n, m) in enumerate(kappa_idx):
        # 1e contribution
        for p in range(num_inactive_orbs + num_active_orbs):
            gradient[idx + shift] += h_int[n, p] * RDM1(m, p, num_inactive_orbs, num_active_orbs, rdm1)
            gradient[idx + shift] -= h_int[p, m] * RDM1(p, n, num_inactive_orbs, num_active_orbs, rdm1)
        # 2e contribution
        for p in range(num_inactive_orbs + num_active_orbs):
            for q in range(num_inactive_orbs + num_active_orbs):
                for r in range(num_inactive_orbs + num_active_orbs):
                    gradient[idx + shift] += (
                        1
                        / 2
                        * g_int[n, p, q, r]
                        * RDM2(m, p, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2)
                    )
                    gradient[idx + shift] -= (
                        1
                        / 2
                        * g_int[p, m, q, r]
                        * RDM2(p, n, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2)
                    )
                    gradient[idx + shift] -= (
                        1
                        / 2
                        * g_int[m, p, q, r]
                        * RDM2(n, p, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2)
                    )
                    gradient[idx + shift] += (
                        1
                        / 2
                        * g_int[p, n, q, r]
                        * RDM2(p, m, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2)
                    )
    return 2 ** (-1 / 2) * gradient


@nb.jit(nopython=True)
def get_orbital_response_metric_sigma(
    kappa_idx: list[tuple[int, int]],
    num_inactive_orbs: int,
    num_active_orbs: int,
    rdm1: np.ndarray,
) -> np.ndarray:
    r"""Calculate the Sigma matrix orbital-orbital block.

    .. math::
        \Sigma_{pq,pq}^{\hat{q},\hat{q}} = \left<0\left|\left[\hat{q}_{pq}^\dagger,\hat{q}_{pq}\right]\right|0\right>

    Args:
        kappa_idx: Orbital parameter indices in spatial basis.
        num_inactive_orbs: Number of inactive orbitals in spatial basis.
        num_active_orbs: Number of active orbitals in spatial basis.
        rdm1: Active part of 1-RDM.

    Returns:
        Sigma matrix orbital-orbital block.
    """
    sigma = np.zeros((len(kappa_idx), len(kappa_idx)))
    for idx1, (n, m) in enumerate(kappa_idx):
        for idx2, (p, q) in enumerate(kappa_idx):
            if p == n:
                sigma[idx1, idx2] += RDM1(m, q, num_inactive_orbs, num_active_orbs, rdm1)
            if m == q:
                sigma[idx1, idx2] -= RDM1(p, n, num_inactive_orbs, num_active_orbs, rdm1)
    return -1 / 2 * sigma


@nb.jit(nopython=True)
def get_orbital_response_vector_norm(
    kappa_idx: list[list[int]],
    num_inactive_orbs: int,
    num_active_orbs: int,
    rdm1: np.ndarray,
    response_vectors: np.ndarray,
    state_number: int,
    number_excitations: int,
) -> float:
    r"""Calculate the orbital part of excited state norm.

    .. math::
        N^{\hat{q}} = \sum_k\left<0\left|\left[\hat{O}_{k},\hat{O}_{k}^\dagger\right]\right|0\right>

    Args:
        kappa_idx: Orbital parameter indices in spatial basis.
        num_inactive_orbs: Number of inactive orbitals in spatial basis.
        num_active_orbs: Number of active orbitals in spatial basis.
        rdm1: Active part of 1-RDM.
        response_vectors: Response vectors.
        state_number: State number counting from zero.
        number_excitations: Total number of excitations.

    Returns:
        Orbital part of excited state norm.
    """
    norm = 0
    for i, (m, n) in enumerate(kappa_idx):
        for j, (t, u) in enumerate(kappa_idx):
            if n == u:
                norm += (
                    response_vectors[i, state_number]
                    * response_vectors[j, state_number]
                    * RDM1(m, t, num_inactive_orbs, num_active_orbs, rdm1)
                )
            if m == t:
                norm -= (
                    response_vectors[i, state_number]
                    * response_vectors[j, state_number]
                    * RDM1(n, u, num_inactive_orbs, num_active_orbs, rdm1)
                )
            if m == t:
                norm += (
                    response_vectors[i + number_excitations, state_number]
                    * response_vectors[j + number_excitations, state_number]
                    * RDM1(n, u, num_inactive_orbs, num_active_orbs, rdm1)
                )
            if n == u:
                norm -= (
                    response_vectors[i + number_excitations, state_number]
                    * response_vectors[j + number_excitations, state_number]
                    * RDM1(m, t, num_inactive_orbs, num_active_orbs, rdm1)
                )
    return 1 / 2 * norm


@nb.jit(nopython=True)
def get_orbital_response_property_gradient(
    x_mo: np.ndarray,
    kappa_idx: list[tuple[int, int]],
    num_inactive_orbs: int,
    num_active_orbs: int,
    rdm1: np.ndarray,
    response_vectors: np.ndarray,
    state_number: int,
    number_excitations: int,
) -> float:
    r"""Calculate the orbital part of property gradient.

    .. math::
        P^{\hat{q}} = \sum_k\left<0\left|\left[\hat{O}_{k},\hat{X}\right]\right|0\right>

    Args:
        x_mo: Property integral in MO basis.
        kappa_idx: Orbital parameter indices in spatial basis.
        num_inactive_orbs: Number of inactive orbitals in spatial basis.
        num_active_orbs: Number of active orbitals in spatial basis.
        rdm1: Active part of 1-RDM.
        response_vectors: Response vectors.
        state_number: State number counting from zero.
        number_excitations: Total number of excitations.

    Returns:
        Orbital part of property gradient.
    """
    prop_grad = 0
    for i, (m, n) in enumerate(kappa_idx):
        for p in range(num_inactive_orbs + num_active_orbs):
            prop_grad += (
                (response_vectors[i + number_excitations, state_number] - response_vectors[i, state_number])
                * x_mo[n, p]
                * RDM1(m, p, num_inactive_orbs, num_active_orbs, rdm1)
            )
            prop_grad += (
                (response_vectors[i, state_number] - response_vectors[i + number_excitations, state_number])
                * x_mo[m, p]
                * RDM1(n, p, num_inactive_orbs, num_active_orbs, rdm1)
            )
    return 2 ** (-1 / 2) * prop_grad


@nb.jit(nopython=True)
def get_orbital_response_hessian_block(
    h: np.ndarray,
    g: np.ndarray,
    kappa_idx1: list[tuple[int, int]],
    kappa_idx2: list[tuple[int, int]],
    num_inactive_orbs: int,
    num_active_orbs: int,
    rdm1: np.ndarray,
    rdm2: np.ndarray,
) -> np.ndarray:
    r"""Calculate Hessian-like orbital-orbital block.

    .. math::
        H^{\hat{q},\hat{q}}_{tu,mn} = \left<0\left|\left[\hat{q}_{tu},\left[\hat{H},\hat{q}_{mn}\right]\right]\right|0\right>

    Args:
        h: Hamiltonian one-electron integrals in MO basis.
        g: Hamiltonian two-electron integrals in MO basis.
        kappa_idx1: Orbital parameter indices in spatial basis.
        kappa_idx2: Orbital parameter indices in spatial basis.
        num_inactive_orbs: Number of inactive orbitals in spatial basis.
        num_active_orbs: Number of active orbitals in spatial basis.
        rdm1: Active part of 1-RDM.
        rdm2: Active part of 2-RDM.

    Returns:
        Hessian-like orbital-orbital block.
    """
    A1e = np.zeros((len(kappa_idx1), len(kappa_idx1)))
    A2e = np.zeros((len(kappa_idx1), len(kappa_idx1)))
    for idx1, (t, u) in enumerate(kappa_idx1):
        for idx2, (m, n) in enumerate(kappa_idx2):
            # 1e contribution
            A1e[idx1, idx2] += h[n, t] * RDM1(m, u, num_inactive_orbs, num_active_orbs, rdm1)
            A1e[idx1, idx2] += h[u, m] * RDM1(t, n, num_inactive_orbs, num_active_orbs, rdm1)
            for p in range(num_inactive_orbs + num_active_orbs):
                if m == u:
                    A1e[idx1, idx2] -= h[n, p] * RDM1(t, p, num_inactive_orbs, num_active_orbs, rdm1)
                if t == n:
                    A1e[idx1, idx2] -= h[p, m] * RDM1(p, u, num_inactive_orbs, num_active_orbs, rdm1)
            # 2e contribution
            for p in range(num_inactive_orbs + num_active_orbs):
                for q in range(num_inactive_orbs + num_active_orbs):
                    A2e[idx1, idx2] += g[n, t, p, q] * RDM2(
                        m, u, p, q, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] -= g[n, p, u, q] * RDM2(
                        m, p, t, q, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] += g[n, p, q, t] * RDM2(
                        m, p, q, u, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] += g[u, m, p, q] * RDM2(
                        t, n, p, q, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] += g[p, m, u, q] * RDM2(
                        p, n, t, q, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] -= g[p, m, q, t] * RDM2(
                        p, n, q, u, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] -= g[u, p, n, q] * RDM2(
                        t, p, m, q, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] += g[p, t, n, q] * RDM2(
                        p, u, m, q, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] += g[p, q, n, t] * RDM2(
                        p, q, m, u, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] += g[u, p, q, m] * RDM2(
                        t, p, q, n, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] -= g[p, t, q, m] * RDM2(
                        p, u, q, n, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
                    A2e[idx1, idx2] += g[p, q, u, m] * RDM2(
                        p, q, t, n, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                    )
            for p in range(num_inactive_orbs + num_active_orbs):
                for q in range(num_inactive_orbs + num_active_orbs):
                    for r in range(num_inactive_orbs + num_active_orbs):
                        if m == u:
                            A2e[idx1, idx2] -= g[n, p, q, r] * RDM2(
                                t, p, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                            )
                        if t == n:
                            A2e[idx1, idx2] -= g[p, m, q, r] * RDM2(
                                p, u, q, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                            )
                        if m == u:
                            A2e[idx1, idx2] -= g[p, q, n, r] * RDM2(
                                p, q, t, r, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                            )
                        if t == n:
                            A2e[idx1, idx2] -= g[p, q, r, m] * RDM2(
                                p, q, r, u, num_inactive_orbs, num_active_orbs, rdm1, rdm2
                            )
    return 1 / 2 * A1e + 1 / 4 * A2e
