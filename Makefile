# Makefile for Telegram Software Library Bot

.PHONY: help install run test lint clean docker-build docker-up docker-down

help: ## Show this help
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies	pip install -r requirements.txt

run: ## Run the bot
	python main.py

test: ## Run tests
	pytest -v

test-cov: ## Run tests with coverage
	pytest --cov=. --cov-report=html --cov-report=term

lint: ## Run linters
	flake8 .
	black --check .
	mypy . --ignore-missing-imports

format: ## Format code
	black .
	isort .

clean: ## Clean up
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .mypy_cache htmlcov .coverage
	rm -rf logs/*.log
	rm -rf temp/*

docker-build: ## Build Docker image
	docker build -t telegram-bot .

docker-up: ## Start Docker containers
	docker-compose up -d

docker-down: ## Stop Docker containers
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f

backup: ## Create database backup
	python -c "from services.backup_service import backup_service; import asyncio; asyncio.run(backup_service.create_backup(None))"

restore: ## Restore from backup
	@echo "Usage: make restore BACKUP=backup_name"
	python -c "from services.backup_service import backup_service; import asyncio; asyncio.run(backup_service.restore_backup(None, '$(BACKUP)'))"

dev-setup: install ## Setup development environment
	pip install -r requirements.txt
	pip install pytest pytest-cov pytest-asyncio black flake8 mypy
	cp .env.example .env
	@echo "Development environment ready!"