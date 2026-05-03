import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

def generate_miami_top10_viz(predictions_path: Path, output_path: Path):
    """Generate a high-fidelity bar chart for the Miami GP Top 10 predictions.
    
    Uses a 'Miami Vice' aesthetic for the visualization.
    """
    if not predictions_path.exists():
        logger.error(f"Predictions file not found at {predictions_path}")
        return

    # Load and filter
    df = pd.read_parquet(predictions_path)
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
    source = Path(settings.reports_dir) / str(predict_year) / "predictions" / f"predictions_lgb_{predict_year}.parquet"
    # New Elite Structure path
    target_dir = Path(settings.reports_dir) / str(predict_year) / "Miami_Grand_Prix" / "results"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "miami_race_preview.png"
    
    generate_miami_top10_viz(source, target)
