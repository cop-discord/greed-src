from asyncio import to_thread as thread
from io import BytesIO
from textwrap import wrap
from typing import Optional

from aiofiles import open as async_open
from aiohttp import ClientSession as Session
from PIL import Image, ImageDraw, ImageFont


class Caption:
    def __init__(self, font_path: Optional[str] = "/root/impact.ttf"):
        self.font_path = font_path

    async def download_image(self, url: str) -> bytes:
        async with Session() as session:
            async with session.get(url) as response:
                data = await response.read()
        return data

    async def get_bytes(self, fp: str) -> bytes:
        async with async_open(fp, "rb") as file:
            data = await file.read()
        return data

    async def create_captioned_image(
        self, image_input: str, caption_text: str, max_char_per_line=25, border_width=2
    ):
        """
        Creates a new image with the caption added above the original image,
        with a white background and black text with a black border, similar to iFunny.

        Args:
                image_path: Path to the input image (GIF or PNG).
                caption_text: Text for the caption.
                font_path: Path to a font file (optional).
                max_char_per_line: Maximum characters allowed per line in the caption.
                border_width: Width of the black border around the caption text (optional).
        """

        # Load the image
        def do_caption(image_path, caption_text):
            image = Image.open(image_path)
            output = BytesIO()
            # Process caption text
            wrapped_text = wrap(caption_text, max_char_per_line)

            font = ImageFont.truetype(
                self.font_path, 20
            )  # Create the font object first
            text_height = len(wrapped_text) * (
                font.size + border_width
            )  # Now you can use font
            new_height = (
                image.height + text_height + (border_width * 2)
            )  # Add top & bottom border padding

            # Create a new canvas with sufficient height and white background
            new_image = Image.new(
                "RGBA", (image.width, new_height), (255, 255, 255)
            )  # White background

            # Paste original image onto the new canvas

            # Draw caption with black text and black border
            draw = ImageDraw.Draw(new_image)  # Adjust font size and path

            y_text = (
                new_height - text_height
            )  # Start text at bottom (adjust for padding)
            for line in wrapped_text:
                # Draw black border slightly offset
                draw.text(
                    (10 - border_width, y_text - border_width),
                    line,
                    (0, 0, 0),
                    font=font,
                )
                # draw.text((10, y_text), line, (0, 0, 0), font=font)  # Draw black text on top
                y_text += font.size + border_width  # Adjust y position for next line
            new_image.paste(image, (0, 0))
            # Save the final image with caption
            try:
                new_image.save(output, format=image.format)
            except:
                new_image.save(output, format="PNG")
            output.seek(0)
            return output

        if image_input.startswith("https://"):
            image_ = await self.download_image(image_input)
        else:
            image_ = await self.get_bytes(image_input)
        _image = BytesIO(image_)
        _image.seek(0)
        return await thread(do_caption, _image, caption_text)
