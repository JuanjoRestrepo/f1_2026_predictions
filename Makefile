# =============================================================================
# F1 2026 Prediction Pipeline - Master Control Console
# =============================================================================
# Standard orchestration for Ingestion, Prediction, and Reporting.
# Uses Docker Compose with --rm to ensure a clean workspace at all times.
# =============================================================================

.PHONY: help build ingest predict report clean full-pipeline

# Default variables
YEAR ?= 2025
TRAIN_YEARS ?= 2022 2023 2024
PREDICT_YEAR ?= 2026
TEST_YEAR ?= 2024

help:
	@echo "🏎️  F1 2026 Prediction Pipeline Console"
	@echo "---------------------------------------"
	@echo "Usage:"
	@echo "  make build             - Build the Docker pipeline image"
	@echo "  make ingest YEAR=2025  - Ingest a full season (Bronze->Silver->Gold)"
	@echo "  make predict           - Run 2026 predictions using 2022-2025 data"
	@echo "  make report            - Generate the full SHAP technical report"
	@echo "  make clean             - Remove all orphan containers and temp artifacts"
	@echo "  make full-pipeline     - Run the complete flow: Ingest -> Predict -> Report"
	@echo ""
	@echo "Examples:"
	@echo "  make ingest YEAR=2025"
	@echo "  make predict TRAIN_YEARS=\"2022 2023\" PREDICT_YEAR=2024"

build:
	docker-compose build

ingest:
	@echo "🚀 Ingesting Season $(YEAR)..."
	docker-compose run --rm pipeline python scripts/ingest_season.py --year $(YEAR)

predict:
	@echo "🔮 Running Predictions for $(PREDICT_YEAR)..."
	docker-compose run --rm pipeline python scripts/predict_season.py \
		--train-years $(TRAIN_YEARS) \
		--predict-year $(PREDICT_YEAR)

report:
	@echo "📊 Generating Technical Report (Test Year: $(TEST_YEAR))..."
	docker-compose run --rm pipeline python scripts/generate_reports.py \
		--train-years $(TRAIN_YEARS) \
		--test-year $(TEST_YEAR) \
		--shap

clean:
	@echo "🧹 Cleaning up orphan containers and temporary files..."
	docker-compose down --remove-orphans
	rm -rf .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +

full-pipeline: build ingest predict report
	@echo "✅ Full pipeline execution complete. Check the reports/ directory."
