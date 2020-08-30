class app {

	constructor(modules, invocation){
		languagePluginLoader.then(() => {
			// If you don't require for pre-loaded Python packages, remove this promise below.
			window.pyodide.runPythonAsync("import setuptools, micropip").then(()=>{
				window.pyodide.runPythonAsync("micropip.install('lark-parser')").then(()=>{
					this.fetchSources(modules).then(() => {
						window.pyodide.runPythonAsync("import " + Object.keys(modules).join("\nimport ") + "\n" + invocation + "\n").then(() => this.initializingComplete());
					});
				});
			});
		});
	}

	loadSources(module, baseURL, files) {
		let promises = [];

		for (let f in files) {
			promises.push(
				new Promise((resolve, reject) => {
					let file = files[f];
					let url = (baseURL ? baseURL + "/" : "") + file;

					fetch(url, {}).then((response) => {
						if (response.status === 200)
							return response.text().then((code) => {
								let path = ("/lib/python3.7/site-packages/" + module + "/" + file).split("/");
								let lookup = "";

								for (let i in path) {
									if (!path[i]) {
										continue;
									}

									lookup += (lookup ? "/" : "") + path[i];

									if (parseInt(i) === path.length - 1) {
										window.pyodide._module.FS.writeFile(lookup, code);
										console.debug(`fetched ${lookup}`);
									} else {
										try {
											window.pyodide._module.FS.lookupPath(lookup);
										} catch {
											window.pyodide._module.FS.mkdir(lookup);
											console.debug(`created ${lookup}`);
										}
									}
								}

								resolve();
							});
						else
							reject();
					});
				})
			);
		}

		return Promise.all(promises);
	}

	fetchSources(modules) {
		let promises = [];

		for( let module of Object.keys(modules) )
		{
			promises.push(
				new Promise((resolve, reject) => {
					fetch(`${modules[module]}/files.json`, {}).then((response) => {
						if (response.status === 200) {
							response.text().then((list) => {
								let files = JSON.parse(list);

								this.loadSources(module, modules[module], files).then(() => {
									resolve();
								})
							})
						} else {
							reject();
						}
					})
				}));
		}

		return Promise.all(promises).then(() => {
			for( let module of Object.keys(modules) ) {
				window.pyodide.loadedPackages[module] = "default channel";
			}

			window.pyodide.runPython(
				'import importlib as _importlib\n' +
				'_importlib.invalidate_caches()\n'
			);
		});
	}

	initializingComplete() {
		document.body.classList.remove("is-loading")
	}
}

(function () {
	window.top.app = new app({"app": "app"}, "import app.app; app.app.start()");
})();
