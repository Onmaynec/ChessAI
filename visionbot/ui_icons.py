"""Small, crisp line icons. Pillow is already a Vision dependency."""
from PIL import Image, ImageDraw

def icon_image(ctk, name, color='#c6c6d5', size=20):
    image=Image.new('RGBA',(96,96))
    draw=ImageDraw.Draw(image)
    def line(points):
        draw.line([(int(x*4),int(y*4)) for x,y in points],fill=color,width=7,joint='curve')
    def rect(x1,y1,x2,y2):
        draw.rounded_rectangle((x1*4,y1*4,x2*4,y2*4),radius=6,outline=color,width=7)
    def circle(x,y,r):
        draw.ellipse(((x-r)*4,(y-r)*4,(x+r)*4,(y+r)*4),outline=color,width=7)
    if name=='home':
        line([(3,11),(12,3),(21,11)]);line([(5,10),(5,21),(10,21),(10,15),(14,15),(14,21),(19,21),(19,10)])
    elif name=='vision':
        circle(12,12,7);circle(12,12,2)
        for points in ([(12,2),(12,6)],[(12,18),(12,22)],[(2,12),(6,12)],[(18,12),(22,12)]):line(points)
    elif name=='analysis':
        for x,y in ((4,14),(10,9),(16,4)):rect(x,y,x+4,21)
    elif name=='log':
        rect(5,3,19,21)
        for y in (8,12,16):line([(8,y),(16,y)])
    elif name=='settings':
        circle(12,12,7);circle(12,12,3)
        for points in ([(12,1),(12,5)],[(12,19),(12,23)],[(1,12),(5,12)],[(19,12),(23,12)],[(4,4),(7,7)],[(17,17),(20,20)],[(4,20),(7,17)],[(17,7),(20,4)]):line(points)
    elif name=='model':
        line([(3,8),(12,3),(21,8),(12,13),(3,8)])
        line([(3,12),(12,17),(21,12)]);line([(3,16),(12,21),(21,16)])
    elif name=='side':
        circle(12,7,3);line([(12,10),(8,15),(8,17),(5,17),(5,21),(19,21),(19,17),(16,17),(16,15),(12,10)])
    else:
        circle(12,12,8)
    return ctk.CTkImage(light_image=image,dark_image=image,size=(size,size))
