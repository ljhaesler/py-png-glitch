# PNG Glitch

This is a fairly straightforward tool to perform glitches on PNG files.
To use it, you simply need to download the files and run glitch.py with python3 or py depending on your python install.
A very straightforward use case would be:

`python3 glitch.py path/to/png.png -f 1`

Doing this will write the Sub filter to every scanline of the PNG (It will **NOT** create a copy of the PNG before doing this). The only required flag for this tool is the `-f` flag, all other flags are optional.

```
usage: png-glitch [-h] -f {0,1,2,3,4,random} [-s SECTIONS] [-r] [--ffmpeg] [-b BITWISE] [-c CONVERT] [-m] [-u] filename

Simple-ish tool to corrupt and mess with png files.

positional arguments:
  filename

options:
  -h, --help            show this help message and exit
  -f, --filter {0,1,2,3,4,random}
                        Sets the filter type of each scanline in the PNG file the specified filter type. The random value will select a filter at random, which can be used alongside the -s flag.
  -s, --sections SECTIONS
                        Defines how many sections to split the PNG into, with each section having a random filter type. To be used alongside '-f random' only.
  -r, --redraw          Will redraw each pixel inside each scanline with an increasing offset. This shifts the image diagonally, which can create some nice effects alongside various filters.
  --ffmpeg              This compresses the PNG, ensuring that each scanline is given the same filter. This can help create unique effects on the PNG, and also allow for more consistent output results.
  -b, --bitwise BITWISE
                        Performs various bitwise operations on the unfiltered bytes extracted from the PNG. This can create very unique effects. The supported arguments are: or, xor, and, rshift, lshift, invert, swap, noise
  -c, --convert CONVERT
                        This argument is used to convert between PNG colortypes. It will pad/delete bytes from the unfiltered png bytes as needed. Note that if converting to a 'smaller' colortype, the deleted byte data is
                        deleted permanently.
  -m, --messy           A 'messy' conversion will create a unique scattering/offset effect on the image. This will essentially pad a colortype 2 image with extra bytes to create a colortype 6 image, but then read it as if
                        it were still a colortype 2 image.
  -u, --undo            Undoes a 'messy' conversion. Essentially performs the inverse operations as -m.
```
