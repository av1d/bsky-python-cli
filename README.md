# bsky-python-cli

bsky-python-cli is an an unofficial command-line client for posting to Bluesky.

Supports mentions, hyperlinks, website card (Open Graph meta for embedding in post ('social cards')), multiple images and alt text. For your security this will make a copy of your images with the EXIF data stripped prior to posting.

Does not use an SDK because I hate them.


## Prerequisites
Get your app password here: [https://bsky.app/settings/app-passwords](https://bsky.app/settings/app-passwords)

## Installation
```sh
pip install -r requirements.txt
```
Then edit your settings inside the script.

## Example usage

just text:
```sh
bsky-python-cli.py 'Hello BlueSky'
```
just images:
```sh
bsky-python-cli.py '' '1.png,2.png'
```
with mention and hyperlink:
```sh
bsky-python-cli.py 'This is a script made by @av1d - check out his website https://superscape.org/'
```
with mention and images with alt text:
```sh
bsky-python-cli.py 'Yum @everyone! Check out these cakes' 'straw.png,choc.png,bost.png,poke.png' 'strawberry~chocolate~Boston cream pie~poke cake'
```
everything:
```sh
bsky-python-cli.py 'Example @example https://example.org/' 'example1.png,example2.png' 'alt text for example1.png ~ example2.png text'
```

## Bugs
There are bound to be some, this isn't tested extensively. Open an issue or create a pull request if you find one.

## Changelog
02.10.2024
- better error handling for some instances
- Updated Open Graph to grab a title from title tag if og:title is unavailable.
- Grabs favicon if no og:image, then trys first <img> if no favicon before setting image to none.
- various other updates

## Legal
This software is neither created nor endorsed by Bluesky. Use at your own risk.
