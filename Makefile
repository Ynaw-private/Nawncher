PREFIX ?= $(HOME)/.local
BUILDS ?= $(HOME)/builds

.PHONY: help install install-system uninstall purge dist check clean

help:
	@printf '%s\n' \
		'Nawncher 2.0.0' \
		'' \
		'  make install          Instala para el usuario en ~/.local' \
		'  make install-system   Instala para todo el sistema en /usr (sudo)' \
		'  make uninstall        Desinstala (conserva ~/.nawncher)' \
		'  make purge            Desinstala y borra ~/.nawncher' \
		'  make dist             Genera .deb, .rpm y paquete de Arch en ~/builds' \
		'  make check            Comprueba sintaxis y compila el Python' \
		'  make clean            Borra build/, .build-tools/ y __pycache__'

install:
	./install.sh --user --prefix "$(PREFIX)"

install-system:
	sudo ./install.sh --system

uninstall:
	./install.sh --user --prefix "$(PREFIX)" --uninstall

purge:
	./install.sh --user --prefix "$(PREFIX)" --uninstall --purge

dist:
	NAWNCHER_OUTPUT_DIR="$(BUILDS)" ./build-packages.sh

check:
	bash -n install.sh
	bash -n install-online.sh
	bash -n build-packages.sh
	python3 -c "compile(open('src/nawncher.py', encoding='utf-8').read(), 'src/nawncher.py', 'exec')"

clean:
	rm -rf build .build-tools src/__pycache__
