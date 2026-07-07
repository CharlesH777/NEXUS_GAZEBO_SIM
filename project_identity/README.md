# Project Identity Assets

This folder groups reusable project identity files for NEXUS projects.

## Layout

```text
project_identity/
├── logo/
│   ├── nexus_logo.py
│   ├── nexus_logo.png
│   └── play_logo_intro.sh
└── legal/
    ├── LICENSE
    ├── NOTICE.md
    ├── CODE_OF_CONDUCT.md
    └── CONTRIBUTING.md
```

## Reuse

Copy this folder into another project, then update the project name, author,
copyright year, third-party notices, and any README links.

To play the intro logo from a repository root:

```bash
bash project_identity/logo/play_logo_intro.sh 30 golden
```

The license files are templates for this project family. They do not grant
permission by themselves; the target project owner must approve and adapt them.
