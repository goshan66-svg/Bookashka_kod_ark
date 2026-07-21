[app]
source.dir = .
title = GuestPlayer
package.name = guestplayer
package.domain = org.test

source.include_exts = py,png,jpg,txt,json
source.include_patterns = pattern1.jpg, pattern2.txt

version = 1.0
orientation = portrait

requirements = python3, kivy, kivymd, requests, pycryptodome, ffpyplayer

android.sdk = 34
android.build_tools = 34.0.0
