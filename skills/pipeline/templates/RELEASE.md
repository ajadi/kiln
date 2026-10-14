# Release checklist — <platform>

- [ ] <store requirement from research/release-<platform>.md>
- [ ] no debug output / placeholders / TODO in shipped paths
- [ ] build audit clean: nothing from ref/ production/ tools/ tests/ design/ research/ ships
- [ ] release export launched outside the editor (`production/builds/release/smoke.json`)
- [ ] 60-minute soak: memory growth < 20 %, no new errors (`production/builds/release/soak.json`)
- [ ] builds signed (Windows Authenticode / macOS notarization) where the store needs it
- [ ] store assets at the store's exact sizes, captured from the real game
- [ ] earlier saves load
- [ ] licence registry clean (`licenses.py build` passes) and credits copied into the game
- [ ] store material from real captures
