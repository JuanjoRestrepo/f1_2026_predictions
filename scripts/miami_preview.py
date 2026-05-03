import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

def generate_miami_top10_viz(predictions_path: Path, output_path: Path):
    """Create an aesthetic Top 10 visualization from prediction results."""
    # Load data based on extension
    if str(predictions_path).endswith(".csv"):
        df = pd.read_csv(predictions_path)
    else:
        df = pd.read_parquet(predictions_path)

    # Filter for Miami if it's the global file
    miami_df = df[df['EventName'] == 'Miami Grand Prix']
    
    if miami_df.empty:
        logger.warning("No Miami Grand Prix data found. Showing Overall 2026 Season Top 10.")
        plot_df = df
        title = "SEASON 2026: TOP 10 PERFORMANCE (Current Form)"
    else:
        plot_df = miami_df
        title = "MIAMI GP 2026: PREDICTED TOP 10 (Race Pace)"

    # Calculate median lap time per driver
    standings = plot_df.groupby(['Driver', 'Team'])['predicted_laptime_lgb_s'].median().reset_index()
    standings = standings.sort_values('predicted_laptime_lgb_s').head(10)

    # Visualization Setup
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 7))
    
    # Custom Miami Palette
    barplot = sns.barplot(
        data=standings,
        x='predicted_laptime_lgb_s',
        y='Driver',
        hue='Team',
        palette="magma",
        ax=ax
    )

    # Styling
    ax.set_title("MIAMI GP 2026: PREDICTED TOP 10 (Race Pace)", fontsize=18, fontweight='bold', color='#00F5FF', pad=20)
    ax.set_xlabel("Predicted Median Lap Time (seconds)", fontsize=12, color='#FF69B4')
    ax.set_ylabel("Driver", fontsize=12, color='#FF69B4')
    
    # Adjust X axis to highlight small differences
    min_time = standings['predicted_laptime_lgb_s'].min()
    max_time = standings['predicted_laptime_lgb_s'].max()
    ax.set_xlim(min_time - 0.5, max_time + 0.5)

    # Add lap time labels on bars
    for i, p in enumerate(ax.patches):
        width = p.get_width()
        if width > 0:
            ax.text(width + 0.05, p.get_y() + p.get_height()/2, f'{width:.3f}s', 
                    va='center', fontsize=11, fontweight='bold', color='white')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    logger.info(f"Miami Preview visualization saved to: {output_path}")

if __name__ == "__main__":
    settings = get_settings()
    predict_year = 2026
    
    # Try local simulation results first
    miami_results = Path(settings.reports_dir) / str(predict_year) / "Miami_Grand_Prix" / "results" / "predictions.csv"
    season_parquet = Path(settings.reports_dir) / str(predict_year) / "predictions" / f"predictions_lgb_{predict_year}.parquet"
    
    if miami_results.exists():
        logger.info("Using Miami Simulation results for preview.")
        source = miami_results
    else:
        logger.info("Falling back to Season Parquet.")
        source = season_parquet
    # New Elite Structure path (Preview folder)
    target_dir = Path(settings.reports_dir) / str(predict_year) / "Miami_Grand_Prix" / "preview"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "miami_race_preview.png"
    
    generate_miami_top10_viz(source, target)
