# Immediate return-leg bundles (E1)

An experimental variant of [`all_in`](../all_in/README.md): **instant chain formation**, with no new waiting rule.
It builds chains by cheapest insertion into the current route rather than always appending to the end. It reuses
`strategies.chain_opt`'s `RouteBundler`; all admission, pricing, dawn fees and event handling stay unchanged.

From a separate working tree:

```sh
uv run strategies/return_legs/dispatch.py --level 8 --seed tour-r1-d0cceb91
```

Saved weeks are labelled policy `return-legs`. This is experiment E1, not a replacement for `all_in`.

For comparison, `strategies/solo_chain` uses short cheap-solo exposure before retrying a chain, and
`strategies/informed_chain` varies that chance using actual city/time follow-on demand. See issue #306.
