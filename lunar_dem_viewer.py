import sys
import numpy as np
import rasterio
import pyvista as pv
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout,
    QFileDialog, QLabel, QSlider, QComboBox
)
from PyQt5.QtCore import Qt


class LunarDEMViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lunar DEM 3D Viewer 🌕")
        self.setGeometry(200, 200, 450, 300)
        
        # Initialize variables
        self.dem_data = None
        self.transform = None
        self.current_z_scale = 10
        
        # Main layout
        self.layout = QVBoxLayout()
        
        # File selection
        self.file_label = QLabel("No DEM loaded")
        self.layout.addWidget(self.file_label)
        
        self.load_button = QPushButton("📂 Load Lunar DEM (GeoTIFF)")
        self.load_button.clicked.connect(self.load_dem)
        self.layout.addWidget(self.load_button)
        
        # Visualization controls
        self.layout.addWidget(QLabel("\nVisualization Settings:"))
        
        # Z-scale control
        self.z_scale_slider = QSlider(Qt.Horizontal)
        self.z_scale_slider.setRange(1, 50)
        self.z_scale_slider.setValue(self.current_z_scale)
        self.z_scale_slider.valueChanged.connect(self.update_z_scale)
        self.z_scale_label = QLabel(f"Vertical Exaggeration: {self.current_z_scale}x")
        self.layout.addWidget(self.z_scale_label)
        self.layout.addWidget(self.z_scale_slider)
        
        # Colormap selection
        self.layout.addWidget(QLabel("Colormap:"))
        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(["terrain", "viridis", "plasma", "gray", "hot", "moon"])
        self.layout.addWidget(self.cmap_combo)
        
        # Render button
        self.render_button = QPushButton("🖥️ Render 3D View")
        self.render_button.clicked.connect(self.render_3d)
        self.render_button.setEnabled(False)
        self.layout.addWidget(self.render_button)
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.layout.addWidget(self.status_label)
        
        self.setLayout(self.layout)
    
    def update_z_scale(self, value):
        self.current_z_scale = value
        self.z_scale_label.setText(f"Vertical Exaggeration: {value}x")
    
    def load_dem(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Lunar DEM", "", 
            "GeoTIFF Files (*.tif *.tiff);;All Files (*)"
        )
        
        if not file_path:
            return
            
        try:
            with rasterio.open(file_path) as src:
                self.dem_data = src.read(1).astype(np.float32)
                self.transform = src.transform
                
                # Handle NoData values
                if src.nodata is not None:
                    self.dem_data[self.dem_data == src.nodata] = np.nan
                
                dem_min = np.nanmin(self.dem_data)
                dem_max = np.nanmax(self.dem_data)
                
                self.file_label.setText(f"Loaded: {file_path.split('/')[-1]}")
                self.status_label.setText(
                    f"DEM Size: {self.dem_data.shape} | "
                    f"Elevation Range: {dem_min:.2f}m to {dem_max:.2f}m"
                )
                self.render_button.setEnabled(True)
                
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
    
    def render_3d(self):
        if self.dem_data is None:
            self.status_label.setText("❌ No DEM loaded!")
            return
            
        try:
            # Downsample if too large for performance
            max_pixels = 1_000_000  # ~1000x1000
            if self.dem_data.size > max_pixels:
                scale_factor = int((self.dem_data.size / max_pixels) ** 0.5)
                self.dem_data = self.dem_data[::scale_factor, ::scale_factor]
                self.status_label.setText(
                    f"Downsampled DEM to {self.dem_data.shape} for performance"
                )
            
            # Create grid coordinates
            rows, cols = self.dem_data.shape
            x = np.arange(cols) * abs(self.transform.a) + self.transform.c
            y = np.arange(rows) * abs(self.transform.e) + self.transform.f
            xx, yy = np.meshgrid(x, y)
            
            # Apply vertical exaggeration
            zz = self.dem_data * self.current_z_scale
            
            # Create PyVista grid
            grid = pv.StructuredGrid(xx, yy, zz)
            
            # Normalize elevation for coloring
            dem_min, dem_max = np.nanmin(self.dem_data), np.nanmax(self.dem_data)
            elevation = (self.dem_data - dem_min) / (dem_max - dem_min)
            grid.point_data["Elevation"] = elevation.ravel(order="F")
            
            # Create plotter with lunar-appropriate settings
            plotter = pv.Plotter(window_size=[800, 600])
            plotter.add_text(
                "Lunar DEM Visualization\n(Vertical Exaggeration: "
                f"{self.current_z_scale}x)",
                font_size=10,
                position="upper_left"
            )
            
            # Add DEM surface
            cmap = self.cmap_combo.currentText()
            if cmap == "moon":
                # Custom grayscale colormap that looks lunar
                from pyvista import make_cmap
                cmap = make_cmap({
                    0.0: [0.1, 0.1, 0.2],    # Dark shadows
                    0.5: [0.5, 0.5, 0.5],    # Mid grays
                    1.0: [0.9, 0.9, 0.8]     # Bright regolith
                })
            
            plotter.add_mesh(
                grid,
                scalars="Elevation",
                cmap=cmap,
                show_edges=False,
                smooth_shading=True,
                scalar_bar_args={"title": "Normalized Elevation"}
            )
            
            # Configure lunar-appropriate lighting
            plotter.set_background("black")
            light = pv.Light(position=(0, 0, 1), light_type='scene light')
            light.intensity = 0.8
            plotter.add_light(light)
            
            # Set camera to isometric view
            plotter.view_isometric()
            
            # Show the plot
            plotter.show()
            
        except Exception as e:
            self.status_label.setText(f"❌ Rendering error: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern UI style
    
    viewer = LunarDEMViewer()
    viewer.show()
    
    sys.exit(app.exec_())