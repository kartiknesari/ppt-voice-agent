# Start Project

## 1. Clone Repository
```
git clone -b Relative-imports https://github.com/kartiknesari/ppt-voice-agent.git
```
## 2. Download Dependencies
```
uv sync
uv run python -m src.agent download-files
```
## 3. Run in development mode
```
uv run python -m src.agent dev
```
## 4. Run in production mode
```
uv run python -m src.agent start
```
