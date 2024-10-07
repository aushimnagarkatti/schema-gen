# Schema-gen

## Examples

### Example to aggregate multiple JSON schemas which reference each other with $ref:

`python3 schemagen.py json_master -s json_schema.json -d examples`

### Example to convert a clean json schema (with no refs) into XML

1. `python3 schemagen.py json_to_xml -s final_out.json -a sections `   
2. `python3 schemagen.py json_to_xml -s final_out.json -x "XML header" -f "XML footer" -p "XmlBaseType" -a sections`
