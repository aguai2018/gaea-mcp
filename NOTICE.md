# Notices and third-party terms

## Relationship to QuadSpinner

This project is an **independent, unofficial integration**. It is not
affiliated with, endorsed by, sponsored by, or supported by QuadSpinner.

"Gaea" and "QuadSpinner" are trademarks of QuadSpinner AB. This project
contains **no QuadSpinner code, binaries or assets**. It interoperates with a
licensed installation of Gaea 2 that the user supplies and installs
themselves.

## You need your own Gaea licence

Using this project requires a valid Gaea 2 licence. Note that Gaea's GUI and
its Build Swarm **each consume a licence seat**, which is the single most
important operational fact about automating Gaea — see
`skill/gaea-terrain/reference/BUILD.md`.

This project does not circumvent, modify or bypass Gaea's licensing in any way.
It drives the publicly exposed user interface of a legitimately installed copy.

## Copernicus DEM data

The optional helper `gaea_fetch_copernicus_dem` downloads elevation tiles from
the **Copernicus DEM GLO-30** product, distributed through AWS Open Data.

- Product page: https://registry.opendata.aws/copernicus-dem/
- The data is provided by the European Space Agency and the European
  Commission. Users are responsible for complying with the applicable terms
  of use.
- Attribution: "Contains modified Copernicus DEM GLO-30 data (ESA/EU)".

## Microsoft UI Automation

The GUI automation helper is built against `System.Windows.Automation`
(`Microsoft.WindowsDesktop.App`), part of .NET. See the .NET licence terms.

## Python dependencies

`mcp`, `pillow`, `numpy`, `scipy` and `requests` are used under their
respective licences (MIT / BSD / Apache-2.0).
