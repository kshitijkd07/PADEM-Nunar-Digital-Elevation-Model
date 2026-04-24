import numpy as np
import rasterio
from rasterio.enums import Resampling
from scipy.ndimage import gaussian_filter
from skimage.transform import resize
import matplotlib.pyplot as plt
import time
from tqdm import tqdm

class LunarSfS:
    def __init__(self):
        # Lunar-specific parameters
        self.albedo = 0.12
        self.lambda_param = 0.6
        self.min_elevation = -100
        self.max_elevation = 100

    def load_image(self, path, scale_factor=1.0):
        """Load image with proper georeferencing"""
        with rasterio.open(path) as src:
            if not src.transform.is_identity:
                profile = src.profile
                if scale_factor != 1.0:
                    new_height = int(src.height * scale_factor)
                    new_width = int(src.width * scale_factor)
                    image = src.read(
                        1,
                        out_shape=(1, new_height, new_width),
                        resampling=Resampling.average
                    )
                    profile.update(
                        height=new_height,
                        width=new_width,
                        transform=src.transform * src.transform.scale(
                            (src.width / new_width),
                            (src.height / new_height)
                        )
                    )
                else:
                    image = src.read(1)
            else:
                raise ValueError("Input image lacks georeferencing information")
        
        # Normalization with percentile clipping
        p1, p99 = np.percentile(image, [1, 99])
        image = np.clip(image, p1, p99)
        return (image - p1) / (p99 - p1), profile

    def compute_normals(self, dem, resolution=1.0):
        """Improved normal calculation with edge handling"""
        dy, dx = np.gradient(dem, resolution)
        normal = np.dstack((-dx, -dy, np.ones_like(dem)))
        norm = np.linalg.norm(normal, axis=2, keepdims=True)
        return normal / (norm + 1e-8)

    def lunar_reflectance(self, mu0, mu):
        """Stable lunar reflectance model"""
        return (1 - self.lambda_param) * mu0 + \
               2 * self.lambda_param * (mu0 / (mu0 + mu + 1e-8))

    def solve_sfs(self, image, sun_vector, view_vector, lola_dem=None, iterations=100):
        """Shape-from-Shading with proper scaling"""
        # Initialize with reference DEM if available
        if lola_dem is not None:
            self.min_elevation = np.min(lola_dem)
            self.max_elevation = np.max(lola_dem)
            dem = (resize(lola_dem, image.shape) - self.min_elevation) / \
                  (self.max_elevation - self.min_elevation)
        else:
            dem = np.zeros_like(image)
        
        # Optimization loop
        for i in tqdm(range(iterations), desc="SfS Optimization"):
            normals = self.compute_normals(dem)
            mu0 = np.sum(normals * sun_vector, axis=2).clip(0, 1)
            mu = np.sum(normals * view_vector, axis=2).clip(0, 1)
            shaded = self.lunar_reflectance(mu0, mu) * self.albedo
            
            dem += 0.1 * (image - shaded)
            
            if i % 5 == 0:
                dem = gaussian_filter(dem, sigma=0.5)
        
        # Convert to physical elevations
        if lola_dem is not None:
            dem = dem * (self.max_elevation - self.min_elevation) + self.min_elevation
        else:
            # Default scaling based on lunar terrain
            dem = (dem - np.min(dem)) * 20  # 20m range for craters
        
        return dem

    def save_results(self, dem, profile, output_prefix):
        """Save DEM and visualization with proper georeferencing"""
        # Save GeoTIFF
        with rasterio.open(f"{output_prefix}_dem.tif", 'w', **profile) as dst:
            dst.write(dem.astype(np.float32), 1)
        
        # Visualization
        plt.figure(figsize=(12, 8))
        plt.imshow(dem, cmap='terrain')
        cbar = plt.colorbar(label='Elevation (m)')
        cbar.set_ticks(np.linspace(np.min(dem), np.max(dem), 5))
        plt.title('Lunar DEM from Shape-from-Shading')
        plt.savefig(f"{output_prefix}_visualization.png", dpi=300, bbox_inches='tight')
        plt.close()

if __name__ == "__main__":
    # Configuration
    INPUT_IMAGE = "C:/Users/kshit/Desktop/ch2_tmc_ndn_20250518T1102105953_d_dtm_d18.tif" # Must be georeferenced
    LOLA_REFERENCE = ""  # Optional
    OUTPUT_PREFIX = "C:/Users/kshit/Desktop/lunar_sfs/"
    
    # Sun parameters (must get from image metadata)
    SUN_AZIMUTH = 240.5  # degrees
    SUN_ELEVATION = 40.5  # degrees
    
    # Initialize processor
    processor = LunarSfS()
    
    try:
        # Load data
        print("Loading input image...")
        image, profile = processor.load_image(INPUT_IMAGE, scale_factor=0.25)
        
        # Compute sun vector
        sun_az = np.deg2rad(SUN_AZIMUTH)
        sun_el = np.deg2rad(SUN_ELEVATION)
        sun_vector = np.array([
            np.cos(sun_el) * np.sin(sun_az),
            np.cos(sun_el) * np.cos(sun_az),
            np.sin(sun_el)
        ])
        
        # Load reference DEM if available
        lola_dem = None
        if LOLA_REFERENCE:
            with rasterio.open(LOLA_REFERENCE) as src:
                lola_dem = src.read(1)
        
        # Generate DEM
        print("Running Shape-from-Shading...")
        dem = processor.solve_sfs(
            image,
            sun_vector,
            view_vector=np.array([0, 0, 1]),
            lola_dem=lola_dem,
            iterations=100
        )
        
        # Save results
        processor.save_results(dem, profile, OUTPUT_PREFIX)
        
        print("\nDEM generation successful!")
        print(f"Elevation range: {np.min(dem):.2f}m to {np.max(dem):.2f}m")
        print(f"Results saved to:")
        print(f"- {OUTPUT_PREFIX}_dem.tif")
        print(f"- {OUTPUT_PREFIX}_visualization.png")
    
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("Possible solutions:")
        print("1. Ensure input image has georeferencing information")
        print("2. Verify sun angles are correct")
        print("3. Check that reference DEM (if used) covers the same area")