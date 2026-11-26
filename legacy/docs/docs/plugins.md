Extending ProcessAnalyzer with plugins
======================================

Plugin system
-------------

You can extend several aspects of ProcessAnalyzer with user-defined plugins.


Plugin types
------------

1.  Import plugins: This allows to import data from more file types or remote sources.

3.  Export plugins: This allows to save the data in custom formats.

2.  Action plugins. These plugins appear as a context menu item.


Plugin structure
----------------

Plugins have to be put into the plugins/ folder. Each plugin consists of a separate
directory and must contain an `__init__.py` file as well as a manifest file.


This is an example for a manifest file (manifest.yaml):

``` yaml
name: OpenInExcel action
author: Philipp Temminghoff
version: 0.9.0
api_version: 1.0.0
website: www.uni-wuppertal.de
description: Action to open datasets in Microsoft Excel.
requirements:
  - win32com
platforms:
  - win32
```

* `name`: Name of the Plugin
* `author`: Author of the plugin
* `version`: Plugin version
* `api_version`: Version of the plugin API the plugin is compatible with.
* `website`: link to the website or repository
* `description`: Description of the plugin
* `requirements`: list of PyPi packages the plugin depends on.
* `platforms`: list of platforms the plugin is compatible with. If this tag does not exists,
               it is assumed that the plugin is compatible with all platforms.
...
