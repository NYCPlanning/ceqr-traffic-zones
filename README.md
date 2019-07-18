# ceqr-traffic-zones
A script to simplify the geometry of CEQR traffic zones. 

# Instructions

## Install Requirements
`pip install requirements`

## Run the Script
Add the new traffic zone geometry to  `ceqr-traffic-zones/data`. Then run:

`python simplify_ceqr_traffic_zones.py`

## Fill the holes
There are minor gaps in census boundaries which produce very thin holes in the geometry.  ArcMap's [Integrate](http://desktop.arcgis.com/en/arcmap/10.3/tools/data-management-toolbox/integrate.htm) function does a great job of cleaning these up.

1) Upload `unfilled_simplified_ceqr_traffic_zones.geojson` to Carto.
2) Export as a shapefile.
3) In ArcMap, add the shapefile as a layer.
4) In ArcMap's python console run the command: `arcpy.Integrate_management("unfilled_simplified_ceqr_traffic_zones", 0.0001)`
5) Export the result as a shapefile
6) Zip the files and upload them to Carto. 
