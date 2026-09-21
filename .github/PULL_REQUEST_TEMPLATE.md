## Summary

<!-- What does this PR add or change? Which template(s)? -->

## Type of change

- [ ] New template
- [ ] Fix / update to an existing template
- [ ] Documentation
- [ ] Other

## Contributor checklist

- [ ] Template directory contains all **4 files** (`template.yaml`, `Dockerfile`, `commands.py`, `README.md`)
- [ ] `awesome-templates.yaml` index updated (name / description / repo / path / tags / author / capabilities / status)
- [ ] Directory name == `template.yaml` `name` == index `path`
- [ ] Local install passes: `ebx template install ./<name> --registry-type local`
- [ ] `commands.py` imports cleanly; only required capability groups enabled
- [ ] Capabilities in `template.yaml` match the groups enabled in `commands.py`
- [ ] **No secrets** committed (API keys/tokens/passwords) — placeholders only
- [ ] No build junk (`__pycache__/`, `*.pyc`, `.DS_Store`)
- [ ] Uses current naming: **Easy Sandbox / ebx / easy-sandbox / easy_sandbox / Easy-Sandbox**

## Notes for reviewers

<!-- Anything reviewers should pay attention to. -->
