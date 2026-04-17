# Frontend V2 Field Updates Guardrail

Use this skill whenever editing the Field Updates table logic in:
- `frontendV2/src/components/RightPanel.tsx`
- `frontendV2/src/components/RightPanel.fieldUpdatesRows.test.ts`

## Persistent memory

Always run this validation after any change in row rendering / condition translation:

```bash
cd frontendV2
npm run test:field-updates
```

If the change affects UI behavior or build pipeline, also run:

```bash
cd frontendV2
npm run build
```

## Coverage objective

`test:field-updates` must keep passing for:
- simple `ite` (`if/else`)
- nested `ite` (`if/else if/else`)
- ACL-like `and(src,dst)` branches
- LPM/extract branch rendering (`in X/Y`)
- multi-field row alignment and unchanged fallback (`none`)
- inherited reach condition payload shown in hover
