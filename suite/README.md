# Test suite — pytest API tests vs Toolshop

The suite is the source of the failures the agent triages.

- **`test_smoke.py`** — a realistic **API sanity/smoke suite** (13 checks across
  products, product detail, pagination, search, categories, tree, brands, auth).
  Against the `sprint5-with-bugs` build, 9 pass and **4 fail on genuinely planted
  defects** (confirmed by diffing `sprint5/API` vs `sprint5-with-bugs/API`):
  PATCH handler deleted (405), `/categories` null `parent_id`, `role:admin`
  middleware removed (unauth DELETE → 409), and rentals hidden from the default
  `/products` listing.
- **`test_products.py`** / **`conftest.py`** — the three offline seeded scenarios
  (flaky / regression / environment) used by the fixture-based demo and eval.

## Host app — local with-bugs Toolshop (docker)
In your `practice-software-testing` clone:
```bash
echo "SPRINT=sprint5-with-bugs" > .env
docker compose up -d
docker compose exec laravel-api composer install
docker compose exec laravel-api php artisan migrate:fresh --seed
docker compose exec laravel-api php artisan l5-swagger:generate
# API at http://localhost:8091  (Angular UI :4200, phpMyAdmin :8000)
```
`SPRINT` is a volume-mount selector (no image rebuild). Switch back to the clean
app with `SPRINT=sprint5` + `up -d` + `migrate:fresh --seed`.

## Producing the report the agent consumes (no real CI needed)
```bash
API_BASE_URL=http://localhost:8091 \
  pytest suite/test_smoke.py -p no:randomly --junitxml=eval/failures/live.xml
```
That JUnit XML is exactly what a CI pipeline emits. Run the agent on it:
`python cli.py eval/failures/live.xml`. Hosted alternative (no docker):
`API_BASE_URL=https://api-with-bugs.practicesoftwaretesting.com`.
