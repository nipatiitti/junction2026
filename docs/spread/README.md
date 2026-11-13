# Spread: the organisers' documents

Copies of the challenge documents, taken on 13 November 2026, so they can be read without network access.

- `HANDBOOK.md`: the world, the API and the kits. Read it first.
- `RULES.md`: the full rules. Where the documents differ, the rules are correct.
- `API.md`: every route, event and limit.

The current versions are linked from https://spread.bahnexpress.com/llms.txt. The online rules win over these copies. To refresh the copies:

```sh
curl -fsS --remote-name-all --output-dir docs/spread https://spread.bahnexpress.com/kit/{HANDBOOK,RULES,API}.md
```
