"""Aplanado de superficies 3D: LSCM (inicial) + ARAP (para conservar largos).

Sólo usa numpy y scipy, así funciona también en el navegador (Pyodide).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla


def _marcos_locales(V, F):
    """Coordenadas 2D de cada triángulo en su propio plano (isométricas)."""
    v0, v1, v2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    e1, e2 = v1 - v0, v2 - v0
    l1 = np.linalg.norm(e1, axis=1)
    l1[l1 == 0] = 1e-12
    ex = e1 / l1[:, None]
    n = np.cross(e1, e2)
    nn = np.linalg.norm(n, axis=1)
    area = nn / 2
    nn[nn == 0] = 1e-12
    ey = np.cross(n / nn[:, None], ex)
    X = np.zeros((len(F), 3, 2))
    X[:, 1, 0] = l1
    X[:, 2, 0] = np.einsum("ij,ij->i", e2, ex)
    X[:, 2, 1] = np.einsum("ij,ij->i", e2, ey)
    return X, area, ex, ey


def lscm(V, F, fijos=None):
    n = len(V)
    X, area, _, _ = _marcos_locales(V, F)
    if fijos is None:
        fijos = _dos_puntos_lejanos(V, F)
    i0, i1 = fijos
    d = float(np.linalg.norm(V[i1] - V[i0])) or 1.0

    # W_j = (x_k - x_l) + i (y_k - y_l), con (j, k, l) cíclico
    xs, ys = X[:, :, 0], X[:, :, 1]
    s = np.sqrt(np.maximum(2 * area, 1e-18))
    Wr = np.stack([xs[:, 2] - xs[:, 1], xs[:, 0] - xs[:, 2], xs[:, 1] - xs[:, 0]], 1) / s[:, None]
    Wi = np.stack([ys[:, 2] - ys[:, 1], ys[:, 0] - ys[:, 2], ys[:, 1] - ys[:, 0]], 1) / s[:, None]

    m = len(F)
    filas = np.repeat(np.arange(m), 3)
    cols = F.reshape(-1)
    Mr = sp.csr_matrix((Wr.reshape(-1), (filas, cols)), shape=(m, n))
    Mi = sp.csr_matrix((Wi.reshape(-1), (filas, cols)), shape=(m, n))

    libres = np.setdiff1d(np.arange(n), [i0, i1])
    Up = np.array([[0.0, 0.0], [d, 0.0]])
    Mrf, Mif = Mr[:, libres], Mi[:, libres]
    Mrp, Mip = Mr[:, [i0, i1]], Mi[:, [i0, i1]]
    A = sp.bmat([[Mrf, -Mif], [Mif, Mrf]]).tocsc()
    b = -(sp.bmat([[Mrp, -Mip], [Mip, Mrp]]) @ np.concatenate([Up[:, 0], Up[:, 1]]))
    AtA = (A.T @ A).tocsc() + sp.identity(A.shape[1], format="csc") * 1e-10
    x = spla.spsolve(AtA, A.T @ b)
    k = len(libres)
    uv = np.zeros((n, 2))
    uv[libres, 0], uv[libres, 1] = x[:k], x[k:]
    uv[[i0, i1]] = Up
    return uv


def _dos_puntos_lejanos(V, F):
    borde = vertices_borde(F)
    cand = borde if len(borde) >= 2 else np.arange(len(V))
    P = V[cand]
    a = cand[np.argmax(np.linalg.norm(P - P[0], axis=1))]
    b = cand[np.argmax(np.linalg.norm(P - V[a], axis=1))]
    if a == b:
        b = cand[0] if cand[0] != a else cand[-1]
    return int(a), int(b)


def vertices_borde(F):
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    u, c = np.unique(E, axis=0, return_counts=True)
    return np.unique(u[c == 1])


def arap(V, F, uv, iteraciones=15):
    """As-Rigid-As-Possible: ajusta el aplanado para que los triángulos
    conserven sus medidas reales (largo de costuras ≈ largo en 3D)."""
    n = len(V)
    X, area, _, _ = _marcos_locales(V, F)
    m = len(F)

    # cotangentes del ángulo opuesto a cada arista (i,j) de cada triángulo
    pares = [(0, 1, 2), (1, 2, 0), (2, 0, 1)]
    cot = np.zeros((m, 3))
    for e, (i, j, k) in enumerate(pares):
        a = X[:, i] - X[:, k]
        b = X[:, j] - X[:, k]
        cr = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
        dt = np.einsum("ij,ij->i", a, b)
        cot[:, e] = dt / np.maximum(np.abs(cr), 1e-12)
    w = np.clip(cot, 1e-3, 1e3) / 2

    I = np.concatenate([F[:, i] for i, _, _ in pares])
    J = np.concatenate([F[:, j] for _, j, _ in pares])
    Wv = np.concatenate([w[:, e] for e in range(3)])
    L = sp.coo_matrix((np.concatenate([Wv, Wv, -Wv, -Wv]),
                       (np.concatenate([I, J, I, J]), np.concatenate([I, J, J, I]))),
                      shape=(n, n)).tocsc()
    fijo = 0
    libres = np.arange(1, n)
    Lff = L[libres][:, libres].tocsc()
    try:
        solver = spla.factorized(Lff)
    except Exception:
        solver = lambda r: spla.spsolve(Lff, r)
    Lfp = L[libres][:, [fijo]]

    uv = uv.copy()
    for _ in range(iteraciones):
        # paso local: mejor rotación por triángulo
        U = uv[F]  # m,3,2
        S = np.zeros((m, 2, 2))
        for e, (i, j, _) in enumerate(pares):
            du = U[:, i] - U[:, j]
            dx = X[:, i] - X[:, j]
            S += w[:, e, None, None] * np.einsum("ni,nj->nij", du, dx)
        Us, _, Vt = np.linalg.svd(S)
        R = Us @ Vt
        neg = np.linalg.det(R) < 0
        if neg.any():
            Us[neg, :, 1] *= -1
            R[neg] = Us[neg] @ Vt[neg]
        # paso global
        b = np.zeros((n, 2))
        for e, (i, j, _) in enumerate(pares):
            dx = X[:, i] - X[:, j]
            r = w[:, e, None] * np.einsum("nij,nj->ni", R, dx)
            np.add.at(b, F[:, i], r)
            np.add.at(b, F[:, j], -r)
        for c in range(2):
            rhs = b[libres, c] - (Lfp @ uv[[fijo], c])
            uv[libres, c] = solver(rhs)
    return uv


def distorsion(V, F, uv):
    """Devuelve (estiramiento medio %, estiramiento máx %, triángulos invertidos)."""
    X, area, _, _ = _marcos_locales(V, F)
    U = uv[F]
    Dx = np.stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]], axis=2)  # m,2,2
    Du = np.stack([U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]], axis=2)
    ok = np.abs(np.linalg.det(Dx)) > 1e-14
    Jm = np.einsum("nij,njk->nik", Du[ok], np.linalg.inv(Dx[ok]))
    s = np.linalg.svd(Jm, compute_uv=False)
    dev = np.maximum(np.abs(s[:, 0] - 1), np.abs(s[:, 1] - 1))
    a = area[ok]
    media = float((dev * a).sum() / max(a.sum(), 1e-12)) * 100
    maxima = float(np.percentile(dev, 98)) * 100 if len(dev) else 0.0
    inv = int((np.linalg.det(Jm) < 0).sum())
    return media, maxima, inv


def aplanar(V, F, iteraciones=15):
    uv = lscm(V, F)
    # orientación: triángulos en sentido antihorario visto desde afuera
    U = uv[F]
    cr = ((U[:, 1, 0] - U[:, 0, 0]) * (U[:, 2, 1] - U[:, 0, 1]) -
          (U[:, 1, 1] - U[:, 0, 1]) * (U[:, 2, 0] - U[:, 0, 0]))
    if (cr < 0).sum() > (cr > 0).sum():
        uv[:, 0] *= -1
    if iteraciones > 0:
        uv = arap(V, F, uv, iteraciones)
    return uv
