# ── Inline profiling — sin librerías externas ──────────────────────────────
# Usar cuando sweetviz es overkill (sesiones individuales, exploración rápida).
# pandas .describe() + .info() cubren el 80% del diagnóstico inicial.

import pandas as pd


def quick_profile(df: pd.DataFrame, name: str = "DataFrame") -> None:
    """Imprime un perfil compacto de un DataFrame.

    Args:
        df: DataFrame a perfilar.
        name: Nombre descriptivo para el encabezado del reporte.
    """
    print(f"\n{'=' * 60}")
    print(f"  PROFILE: {name}  |  {df.shape[0]:,} filas × {df.shape[1]} cols")
    print(f"{'=' * 60}")
    print("\n--- dtypes y nulos ---")
    null_summary = pd.DataFrame(
        {
            "dtype": df.dtypes,
            "nulls": df.isnull().sum(),
            "null_%": (df.isnull().mean() * 100).round(2),
            "nunique": df.nunique(),
        }
    )
    print(null_summary[null_summary["nulls"] > 0].to_string())
    print("\n--- describe (numérico) ---")
    print(df.describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).T.to_string())
    print(f"\n--- duplicados: {df.duplicated().sum():,} ---\n")
