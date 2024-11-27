# + tags=["parameters"]
product = None
config_templates: "{{config_templates}}"
config_root: "{{config_root}}"
# -


for key in upstream["spectraframe_*"].keys():
    print(key)

for key in upstream["spectracal_*"].keys():
    print(key)