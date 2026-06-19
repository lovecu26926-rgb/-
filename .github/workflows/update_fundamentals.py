name: Update Fundamentals Cache

on:
  schedule:
    # 한국 시간 오전 6시 (UTC 21:00) - scanner.py 실행 8시간 전에 미리 준비
    - cron: '0 21 * * 1-5'
  workflow_dispatch:  # 수동 실행 가능

jobs:
  update:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install requests pandas yfinance

      - name: Run fundamentals update
        env:
          FMP_API_KEY: ${{ secrets.FMP_API_KEY }}
        run: |
          python update_fundamentals.py

      - name: Commit and push cache file
        run: |
          git config --local user.email "actions@github.com"
          git config --local user.name "GitHub Actions"
          git add fundamentals.json
          git diff --staged --quiet || git commit -m "Update fundamentals cache [skip ci]"
          git push
