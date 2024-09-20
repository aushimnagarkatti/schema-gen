#!/usr/bin/env python3
# coding: utf-8
"""
Allows conversion of multiple json schemas into a single
master schema by replacing $ref(s) with the expanded file contents

Modify certain keys of a schema by applying a transformation

Generate an XML schema from a json schema defined for CPERs

@author: Aushim Nagarkatti
"""

#imports
import json
import os
import xml.dom.minidom 
import argparse

HEADER = '''<?xml version="1.0" encoding="UTF-8"?>
<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
  <edmx:Reference Uri="http://docs.oasis-open.org/odata/odata/v4.0/errata03/csd01/complete/vocabularies/Org.OData.Core.V1.xml">
    <edmx:Include Namespace="Org.OData.Core.V1" Alias="OData"/>
  </edmx:Reference>
  <edmx:Reference Uri="http://redfish.dmtf.org/schemas/v1/RedfishExtensions_v1.xml">
    <edmx:Include Namespace="Validation.v1_0_0" Alias="Validation"/>
    <edmx:Include Namespace="RedfishExtensions.v1_0_0" Alias="Redfish"/>
  </edmx:Reference>
  <edmx:DataServices>
    <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="NvidiaCPER.v1_0_0">
'''
FOOTER = '''
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>'''

class SchemaGenerator:
    
    """ 
    Class for creating a single json schema by combining refs
    and allowing modification of property keys. 
    """
    def __init__(self, rootpath, base_schema):
        """
        Args:
            rootpath (string): Path to directory containing all json schema files
            base_schema (string): Path to root json schema file
        """
        self.ref_paths={}
        self.rootpath = rootpath
        self.base_schema=json.load(open(os.path.join(schema_directory, base_schema)))
        self.map_schemas(rootpath)
        
    def map_schemas(self, schema_dir):
        """
        Create a map of all the json files in the directories below root dir
        Args:
            schema_dir (string): Path to root directory containing all json schema files
        """
        for root, _, files in os.walk(schema_dir):
            for filename in files:
                if filename.endswith(".json"):
                    schema_path = os.path.join(root, filename)
                    self.ref_paths[filename]=schema_path

    def refresolve(self,ref):
        if ref not in self.ref_paths:
            print("Error no ref path named: ", ref) 
            return
        with open(self.ref_paths[ref], 'r') as schema_file:
            return json.load(schema_file)


    def replace_refs(self,schema):
        """
        Replace all references of $ref with actual json file contents
        Args:
            schema (string): Original json schema file as a string
        Returns:
            result (string): transformed json schema file
        """
        if isinstance(schema, dict):
            if '$ref' in schema:
                print(schema)
                ref = os.path.basename(schema['$ref'])
                resolved_schema = self.refresolve(ref)
                replaced_ref = self.replace_refs(resolved_schema)
                replaced_ref.pop("$schema", None)
                return  replaced_ref
            else:
                for key, value in schema.items():
                    schema[key] = self.replace_refs(value)
        elif isinstance(schema, list):
            schema = [self.replace_refs(item) for item in schema]            
            
        return schema

    # Modify named properties in a json schema
    def modify_schema(self, schema, keytomod):
        """
        Replace all references of $ref with actual json file contents
        Args:
            schema (string): Original json schema file as a string
            keytomod (string): A particular json property that needs modification
        Returns:
            result (string): json schema file with modified property
        """
        if isinstance(schema, dict):
            for key, value in schema.items():
                if key == keytomod:
                    propname = schema[key]
                    # Define your own transform in place of capitalize()
                    schema[key] = self.capitalize(propname)
                else:
                    schema[key] = self.modify_schema(value)
            
            return schema
            
        elif isinstance(schema, list):
            schema = [self.modify_schema(item) for item in schema]            
            
        return schema
    
    def capitalize(self, propname):
        return propname[0].upper() + propname[1:]


class JsontoXml:

    """ 
    Class for creating an XML version of a JSON schema.
    Created specifically to transform CPER json schemas into xml.
    Note: Refer to examples/json_schema.json for details
    on json schema fields expected by this script.
    """
    def __init__(self, debug=False, parent_basetype=None, required=False, start_property = 'sections'):
        """
        Args:
            debug (bool): Enables verbose printing of schema and properties in each iteration. Default is False.
            parent_basetype (string): Base type of XML schema, which is referred to by all child properties
            required (bool): Populate only "required" properties of the json schema in the XML. Default is False.
            start_property (string): Change root element of the json schema, so XML will only be a subset. This should
                                    be defined in the "properties" field
        """
        self.typemap = {'integer':"Edm.Int64", 'uint64':"Edm.Int64", 'string':"Edm.String", 'boolean':"Edm.Boolean"}
        self.debug = debug
        # add a parent_basetype to instruct code to always
        # use this as the inferred base data type. Else,
        # the base data type for each property will be its immediate parent
        self.parent_basetype = parent_basetype
        self.required = required
        self.start_property = start_property
        self.error_status_present = False
    
    def jsonschema_to_xml(self, schema, basetype, baseid, prevproperty=""):
        """
        Replace all references of $ref with actual json file contents
        Args:
            schema (string): Original json schema file as a string
            basetype (string): Parent data type of property. Use same as parent_basetype if the entire json schema is being used. 
            baseid (string): Reference to closest ancestor $id property. This is used to provide unique namespaces to repeatable properties. 
        Returns:
            result (string): XML schema for CPER output
        """
        if self.debug:
            print("\n\n\n\n")
            print(json.dumps(schema, indent=1))
            
        if isinstance(schema, dict):
            req = schema.get('required')
            if req:
                assert isinstance(req, list), "request field is not a list"

                if (baseid + basetype).lower() == "errorstatuserrortype":
                    if not self.error_status_present:
                        self.error_status_present = True
                    else:
                        return ("", "")

                props = schema.get('properties')
                if not props:
                    print("'Required' field was found. 'Properties' field not found for: \n", schema)
                    return(1)
                    
                id = schema.get('$id')
                if (id and "namevaluepair" not in id):
                    basetype = self.format_propname(id)
                start,end = self.encode_xml(baseid, basetype, 'base')
                property_xml = start

                # We need a way to return baseid to the parent property when the baseids
                # are encapsulated in a list, like in oneOf[]
                ret_id = None
                if id:
                    baseid = self.format_propname(id)
                    ret_id = baseid
                    self.id = id

                if ('validationbits' in basetype.lower()):
                    baseid+=prevproperty
                    
                xml_ret = ""
                for prop, propval in props.items():
                    if self.required and (prop not in req):
                        continue
                    if self.debug:
                        print(prop)
                    # Get each property
                    if (prop.lower() == 'validationbits'):
                        baseid+=basetype
                    subschema = propval
                    property_xml += self.encode_xml(baseid, prop, 'property', type=subschema['type'], basetype=basetype)
                    xml_ret += self.jsonschema_to_xml(propval, prop, baseid, prevproperty=basetype)[0]
                    
                property_xml += end
                xml_ret += property_xml
                if self.debug:
                    print(xml_ret)
                return (xml_ret,ret_id)


            else: 
                if schema.get('oneOf'):
                    return self.jsonschema_to_xml(schema['oneOf'], basetype, baseid, prevproperty)
                elif schema.get('items'):
                    return self.jsonschema_to_xml(schema['items'], basetype, baseid, prevproperty)
                else:
                    return ("", None)
            
        elif isinstance(schema, list):
            property_xml = ""
            properties_oneof = []
            for i, item in enumerate(schema):
                # print("in oneof, basetype:", basetype, json.dumps(item, indent=1))
                xml, ret_id = self.jsonschema_to_xml(item, basetype, baseid, "")
                property_xml += xml
                if ret_id:
                    properties_oneof.append(ret_id)
                else:
                    idstr = 'cper-json-' + baseid.lower() + '-' + basetype.lower()+ str(i)
                    print("\"$id\": \"" + idstr + "\",")

            #This works only if $id is defined for every oneof[]
            if len(properties_oneof):
                xml,end = self.encode_xml(baseid, basetype, 'base')
                for prop in properties_oneof:
                    print(baseid, prop)
                    xml += self.encode_xml(baseid, prop, 'property', 'object', basetype=basetype)
                
                xml += end
            return (property_xml + xml, None)
    

    def schema_parser(self, schema, basetype="NvidiaCPER", baseid=""):
        """
        Wrapper around jsonschema_to_xml
        Args:
            header (string): XML header to be appended to output
            footer (string): XML footer to be appended to output
            schema (string): Original json schema file as a string
            basetype (string): Parent data type of property. Use same as parent_basetype if the entire json schema is being used. 
            baseid (string): Reference to closest ancestor $id property. This is used to provide unique namespaces to repeatable properties.
                             User should leave this empty.  
        Returns:
            result (string): XML schema for CPER output
        """
        xml_out = HEADER
        start_property = self.start_property
        base_schema = { "required": [start_property], 'properties' : { start_property: {} } }
        while not schema.get(start_property):
            if schema.get('oneOf'):
                schema = schema['oneOf'][0]
                continue
            elif schema.get('required'):
                if start_property in schema['required']:
                    schema = schema['properties']
                    continue
            else:
                print("ERROR could not find ", start_property)
                return
        schema = schema[start_property]
        base_schema['properties'][start_property] = schema
        xml_out += self.jsonschema_to_xml(base_schema, basetype=basetype, baseid=baseid)[0]
        xml_out += FOOTER

        return xml_out

    def get_schema_file(self,filename):
        with open(filename, 'r') as schema_file: 
            schema = json.load(schema_file)
        return schema

    def format_propname(self, name):
        """
        Change how property names are displayed
        Args:
            name (string): Property name
        Returns:
            result (string): Formatted name
        """
        names_l = name.split('-')
        # For CPER schemas, name is of the format 
        # cper-json-error-status or cper-json-firmware-section
        ret=""
        for n in names_l[2:]:
            if n =='section':
                continue
            ret+=n.title()
        return ret
            


    def encode_xml(self, baseid, val, ele, type=None, basetype= None):
        """
        Format XML output 
        Args:
            baseid (string): Reference to closest ancestor $id property. This is used to provide unique namespaces to repeatable properties.
                            User should leave this empty.  
            val (string): Property or Entity name
            ele (string): 'base' for Entity, 'property' for Property
            type (string): Used for converting json type to XML type
            basetype (string): Parent data type of property.
            
        Returns:
            result (string): XML schema for CPER output
        """
        # val = self.format_propname(val)
        entity_name = baseid+ val[0].upper() + val[1:]
        prop_name = val[0].upper() + val[1:]
        prop_type = baseid + val[0].upper() + val[1:]
        if ele == "base":
            # print("in encode_xml: args baseid: %s , val: %s, basetype: %s"%(baseid, val, basetype))
            return "\n      <EntityType Name=\"" + entity_name +"\">\n", "      </EntityType>\n"
        elif ele == "property":
            if self.parent_basetype:
                basetype = self.parent_basetype
            else:
                basetype = basetype[0].upper() + basetype[1:]
            if (type == 'object' or type == 'array'):
                return ("          <Property Name=\"" + prop_name +"\" Type=\"" + basetype + "."  + prop_type + "\"></Property>\n")  
            else:
                return ("          <Property Name=\"" + prop_name +"\" Type=\"" + self.typemap[type] + "\"></Property>\n")
        else:
            print("wrong value for XML element: ", ele)

    def append_to_xml(self, xml, arg):
        return xml + arg

    def validate_xml(self, xmlf):
        entity_names=[]
        with open(xmlf, 'r') as f:
            for line in f:
                if ("EntityType Name" in line):
                    name = line.strip().split('=')[1]
                    if name in entity_names:
                        print("Duplicate: ", name)
                    else:
                        entity_names.append(name)
            



if __name__ == "__main__":

    parser = argparse.ArgumentParser(
                    prog='JsonSchemaToXML',
                    description='Create a master json schema by replacing refs, modify json properties, and convert it to XML.',
                    epilog='Refer to examples/json_schema.json for json schema parameters expected by this program.')
    
  
    subparsers = parser.add_subparsers(dest="subparser_name", required=True)

    parser_a = subparsers.add_parser('json_master', help='Select this option to convert an assortment of json schemas into a single schema by using the $ref variable.')
    parser_b = subparsers.add_parser('json_to_xml', help='Create an XML schema out of a json schema')

    parser_a.add_argument('-v', '--verbose', action='store_true')
    parser_a.add_argument('-s', '--schema', nargs=1, help= "Input json schema", required=True)
    parser_a.add_argument('-d', '--schemadir', nargs=1, help= "Root location of json schema directory", required=True)


    parser_b.add_argument('-v', '--verbose', action='store_true')
    parser_b.add_argument('-s', '--schema', nargs=1, help= "Input json schema", required=True)
    parser_b.add_argument('-p', '--parent-basetype', nargs=1, help= "Basetype for all elements to inherit")
    parser_b.add_argument('-x', '--header', nargs=1, help= "XML header")
    parser_b.add_argument('-f', '--footer', nargs=1, help= "XML footer")
    parser_b.add_argument('-r', '--required', help= "Only consider required fields", action='store_true')
    parser_b.add_argument('-z', '--validate', help= "Validate XML", action='store_true')



    args = parser.parse_args()

    if args.subparser_name == 'json_master':
        print("Creating master json")
        # Master JSON Schema creation
        schema_directory = args.schemadir[0] 

        schema = SchemaGenerator(schema_directory, args.schema[0])

        base = schema.base_schema
        master_schema = schema.replace_refs(base)


        output = "master-schema.json"
        print("Output filename: ", output)
        with open(output, 'w') as f:
            print(json.dumps(master_schema, indent=1), file=f)
            # json.dump(master_schema, f)


    elif args.subparser_name == 'json_to_xml':
        print("Creating json-schema -> xml")
        
        if args.header:
           header = args.header[0]
        else:
            header = ""
        
        if args.footer:
            footer = args.footer[0]
        else:
            footer = ""

        if args.parent_basetype:
            parent_basetype = args.parent_basetype[0]
        else:
            parent_basetype = "NvidiaCPER"
        
        print("header is: ", header)
        print("footer is: ", footer)
        print("parent_basetype is: ", parent_basetype)
        print("required is: ", args.required)

        # #JSON to XML conversion
        xml_obj = JsontoXml(debug=args.verbose, parent_basetype=parent_basetype, required=args.required)

        # logfile='cper-json-full-log.json'
        # masterfile = 'master-schema.json'
        if (args.validate):
            xml_obj.validate_xml(args.schema[0])
            exit(0)

        schema = xml_obj.get_schema_file(args.schema[0])
        output = xml_obj.schema_parser(schema)

        out_file = "master-schema.xml"
        print("Output filename: ", out_file)
        with open(out_file, 'w') as f:
            print(output, file=f)
    
    else:
        exit(1)


