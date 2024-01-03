# bsky-python-cli

bsky-python-cli is an an unofficial command-line client for posting to Bluesky.

Supports mentions, hyperlinks, website card (Open Graph meta for embedding in post ('social cards')), multiple images and alt text. For your security this will make a copy of your images with the EXIF data stripped prior to posting.


## Installation
```sh
pip install -r requirements.txt
```
Then edit your settings inside the script.

## Example usage

just text:
```sh
script.py 'Hello BlueSky'
```
just images:
```sh
script.py '' '1.png,2.png'
```
with mention and hyperlink:
```sh
script.py 'This is a script made by @av1d - check out his website https://superscape.org/'
```
with mention and images with alt text:
```sh
script.py 'Yum @everyone! Check out these cakes' 'straw.png,choc.png,bost.png,poke.png' 'strawberry~chocolate~Boston cream pie~poke cake'
```
everything:
```sh
script.py 'Example @example https://example.org/' 'example1.png,example2.png' 'alt text for example1.png ~ example2.png text'
```

## Bugs
There are bound to be some, this isn't tested extensively. Open an issue or create a pull request if you find one.

## Legal
This software is neither created nor endorsed by Bluesky. Use at your own risk.
