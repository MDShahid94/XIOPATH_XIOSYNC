import cv2
import numpy as np
import base64

class VisionMatcher:
    @staticmethod
    def _decode_base64_image(base64_string: str) -> np.ndarray:
        # Remove data URI prefix if present
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        img_data = base64.b64decode(base64_string)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        
        # Handle alpha channel by blending with white background
        if img is not None and img.shape[-1] == 4:
            alpha_channel = img[:, :, 3] / 255.0
            white_background = np.ones_like(img[:, :, :3], dtype=np.uint8) * 255
            for c in range(0, 3):
                img[:, :, c] = (alpha_channel * img[:, :, c] + (1 - alpha_channel) * white_background[:, :, c])
            img = img[:, :, :3]
            
        return img

    @staticmethod
    def match_template(full_page_base64: str, template_base64: str, threshold: float = 0.8) -> dict:
        """
        Searches for a template image inside a full page image.
        Returns the center (x, y) coordinates if a match is found with confidence >= threshold.
        """
        try:
            full_img = VisionMatcher._decode_base64_image(full_page_base64)
            template_img = VisionMatcher._decode_base64_image(template_base64)

            # Perform template matching
            res = cv2.matchTemplate(full_img, template_img, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= threshold:
                h, w = template_img.shape[:2]
                top_left = max_loc
                
                # Calculate center coordinates
                center_x = top_left[0] + w // 2
                center_y = top_left[1] + h // 2
                
                return {
                    "success": True,
                    "x": center_x,
                    "y": center_y,
                    "confidence": float(max_val)
                }
            
            return {"success": False, "confidence": float(max_val)}
        except Exception as e:
            return {"success": False, "error": str(e)}
