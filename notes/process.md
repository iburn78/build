### get_item(key)
#### not existing case
- just creating json file

#### existing and loaded case
- process update
    - check if component_namelist or or keylist/namelist is changed, if component_namelist or keylist/namelist is given
    - auto-create elements in the item (if not "reviewed" for info-section)
    - financials_section is used as is

#### existing but failed to load case
- try retrieve "reviewed" info_section from existing_json and financials_section (info_section is unique in item)
- creating json file

#### common
- if update == True or changed (updated or created), save to file
- manager keeps item in its dict


### json_models
#### Value Chain
- vm: ValueChainManager
- vm.get_item(key, component_namelist)
- no cascading json creation(###_)

#### Component
- cm: ComponentManager
- cm.get_item(key, keylist or namelist)
- no cascading json creation(###_)

#### Profile
- pm: ProfileManager
- pm.get_item(key)
- no cascading json creation(###_)


### SectorAnalysis().process(json_model)
- get endkeys: profile keys(codes) or segment keys
- duplication should be removed here (###_ not yet implemented)
- gather financials for endkeys
    - segment: get profile data and adjust (###_ not yet implemented)
    - profile: get profile data
    - component/valuechain: get endkey data list
- all added up / perform analysis
- for all endkeys: 
    ###_ currently if item is...
    - segment: nothing happens
    - profile: build segment sas if profile info-section is reviewed (first save sas, and then load from file)
    - component: *** code get_item used *** (###_ needs fix: 1. not only code, but also segment, 2. segment cannot use get_item)
    (recursive json creation here)
    - valuechain: component get_item used (recursivity)

