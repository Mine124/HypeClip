import os
from PIL import Image, ImageDraw, ImageFilter

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

grad = Image.new("RGBA", (S, S))
gp = grad.load()
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S)
        gp[x, y] = (int(109 - 75 * t), int(40 + 160 * t), int(217 + 21 * t), 255)

mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([32, 32, S - 32, S - 32], radius=210, fill=255)
img.paste(grad, (0, 0), mask)

inner = Image.new("RGBA", (S, S), (10, 11, 18, 235))
mask2 = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask2).rounded_rectangle([96, 96, S - 96, S - 96], radius=150, fill=255)
img.paste(inner, (0, 0), mask2)

bolt = [(585, 120), (300, 560), (480, 560), (415, 904), (724, 430),
        (520, 430), (660, 120)]
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(glow).polygon(bolt, fill=(167, 139, 250, 120))
glow = glow.filter(ImageFilter.GaussianBlur(28))
img = Image.alpha_composite(img, glow)
ImageDraw.Draw(img).polygon(bolt, fill=(255, 255, 255, 255))

out = os.path.join(os.path.dirname(__file__), "icon.ico")
img.resize((256, 256)).save(out,
    sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("icon.ico written")