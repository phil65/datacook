define BROWSER_PYSCRIPT
import os, webbrowser, sys
try:
    from urllib import pathname2url
except:
    from urllib.request import pathname2url
path = "file:" + pathname2url(os.path.abspath(sys.argv[1]))
print(path)
webbrowser.open(path)
endef
export BROWSER_PYSCRIPT
BROWSER := python -c "$$BROWSER_PYSCRIPT"


build: ## builds the documentation
	poetry run mkdocs build

serve: ## run html server watching file changes in realtime
	python -c "import webbrowser; webbrowser.open('http://127.0.0.1:8000')"
	poetry run mkdocs serve
