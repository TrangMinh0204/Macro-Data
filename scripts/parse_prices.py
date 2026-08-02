name: Price Data (Job B)

on:
  schedule:
    - cron: "15 11 * * 1-5"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  fetch-price:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install deps
        run: pip install requests pyyaml

      - name: Tai va chon ngay du lieu
        run: python scripts/price_collector.py

      - name: Parse va cache CSV
        run: python scripts/parse_prices.py

      - name: Commit du lieu gia va data-health
        if: always()
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/prices output/data-health.md
          if git diff --cached --quiet; then
            echo "Khong co thay doi de commit"
          else
            git commit -m "Cap nhat gia/data-health ${PRICE_DATE} (Job B)"
            git push
          fi
