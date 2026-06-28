# ── ModishLog local dev ───────────────────────────────────────────────────────
# Normal workflow:
#   make up      → start the app (seconds, no rebuild)
#   make down    → stop everything
#   make build   → only after requirements.txt / package.json / Dockerfile change
#   make logs    → tail all service logs
#   make test    → run backend pytest suite
#
# When Docker gets corrupted:
#   make recover → clean corrupted layers and restart

.PHONY: up down build rebuild logs shell test e2e migrate prune recover

# ── Day-to-day ────────────────────────────────────────────────────────────────

up:
	@colima start 2>/dev/null; colima status 2>/dev/null | grep -q Running || { echo "colima failed to start"; exit 1; }
	@docker compose up -d --wait
	@docker compose exec backend alembic upgrade head
	@echo ""
	@echo "  Frontend : http://localhost:4200"
	@echo "  API      : http://localhost:8000"
	@echo "  Swagger  : http://localhost:8000/docs"

down:
	@docker compose down

logs:
	@docker compose logs -f

# ── Rebuild — only needed when deps or Dockerfiles change ─────────────────────

build:
	@docker compose build

rebuild: build up

# ── Utilities ─────────────────────────────────────────────────────────────────

migrate:
	@docker compose exec backend alembic upgrade head

shell:
	@docker compose exec backend bash

test:
	@docker compose exec backend pytest tests/ --tb=short -q

e2e:
	@docker compose exec frontend npx playwright test

# ── Maintenance ───────────────────────────────────────────────────────────────

# Run periodically to keep the Colima VM disk healthy
prune:
	@docker system prune -f

# Corrupted Docker layers (input/output error during build) — removes only
# this project's images and the shared build cache. Volumes (DB data) are kept.
recover:
	@echo "Stopping services..."
	@docker compose down 2>/dev/null || true
	@echo "Removing modishlog images and build cache..."
	@docker compose down --rmi all 2>/dev/null || true
	@docker builder prune -f
	@echo "Restarting..."
	@$(MAKE) up
