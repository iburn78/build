# build process

## get_item(key)

### not existing case

- just creating json file

### existing and loaded case

- process update
  - check if component_namelist or or keylist/namelist is changed, if component_namelist or keylist/namelist is given
  - auto-create elements in the item (if not "reviewed" for info-section)
  - financials_section is used as is

### existing but failed to load case

- try retrieve "reviewed" info_section from existing_json and financials_section (info_section is unique in item)
- creating json file

## json_models

### Value Chain

- vm: ValueChainManager
- vm.get_item(key, component_namelist)
- cascading json creation

### Component

- cm: ComponentManager
- cm.get_item(key, keylist or namelist)
- cascading json creation

### Profile

- pm: ProfileManager
- pm.get_item(key)
- cascading json creation

### SectorAnalysis().process(json_model)

- get endkeys: profile keys(codes) or segment keys
- gather financials for endkeys
- all added up / perform analysis
