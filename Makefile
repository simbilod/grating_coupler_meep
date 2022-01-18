
install:
	pip install -r requirements.txt --upgrade
	pip install -r requirements_dev.txt --upgrade
	pip install -e .
	conda config --add channels conda-forge
	conda install -y pymeep
	pre-commit install

link:
	pip install -e .
	pre-commit install

test:
	pytest

cov:
	pytest --cov= optio

mypy:
	mypy . --ignore-missing-imports

lint:
	flake8

pylint:
	pylint optio

lintd2:
	flake8 --select RST

lintd:
	pydocstyle optio

doc8:
	doc8 docs/

update:
	pur

update2:
	pre-commit autoupdate --bleeding-edge
