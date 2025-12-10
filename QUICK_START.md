# OBPCut Hatching System - Quick Start Guide

## 5-Minute Quick Start

### 1. Load a Model
```
File → Open → Select your STEP/IGES file
```

### 2. Switch to Slice Mode
```
Click "Slice Mode" button (bottom left)
```

### 3. Configure Hatching
```
Tools → Hatching Parameters (or Ctrl+H)

Recommended Settings for SLM:
- Hatch Spacing: 0.1 mm
- Hatch Angle: 0°
- Layer Rotation: 67°
- Enable Contours: ✓
- Scan Speed: 1000 mm/s
- Power Level: 1.0
- Bidirectional: ✓
- Optimize Path: ✓
```

### 4. Generate
```
Click "Generate Hatching" button
Wait for completion message
View statistics in dialog
```

### 5. Visualize
```
- Red lines = Contours
- Blue lines = Infill
- Use scrollbar to navigate layers
- Mouse wheel to change layers
```

### 6. Export
```
Tools → Export to OBP (or Ctrl+E)
Choose location and filename
Save as .obp or .json
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+O | Open CAD file |
| Ctrl+H | Hatching Parameters |
| Ctrl+E | Export to OBP |
| Mouse Wheel | Navigate layers (in slice mode) |
| Left Drag | Rotate view |
| Middle Drag | Pan view |
| Right Drag | Zoom view |

## Hatching Parameters Explained

### Basic Parameters

**Hatch Spacing** (mm)
- Distance between parallel scan lines
- Smaller = denser fill, slower build
- Typical: 0.05-0.2 mm
- SLM typical: 0.1 mm

**Hatch Angle** (degrees)
- Base angle for first layer
- 0° = horizontal lines
- 45° = diagonal lines
- Typical: 0° or 45°

**Layer Rotation** (degrees)
- Rotation increment per layer
- Reduces anisotropy
- Typical: 67° (common in SLM)
- 90° creates checkerboard effect

**Border Offset** (mm)
- Inward offset from contour
- Prevents overlap with contour
- Typical: 0-0.1 mm

### Contour Parameters

**Enable Contours**
- Include perimeter scan lines
- Usually enabled for strength
- Can disable for pure infill

**Contour Count**
- Number of contour passes
- More passes = stronger walls
- Typical: 1-3

### Process Parameters

**Scan Speed** (mm/s)
- Laser/beam travel speed
- Affects energy input
- SLM typical: 500-1500 mm/s

**Power Level** (0-1)
- Normalized power value
- 1.0 = full power
- Can vary per layer/region

### Advanced Options

**Bidirectional Scan**
- Alternate scan direction per line
- Faster build time
- Usually enabled

**Optimize Path**
- Minimize travel distance
- Greedy nearest-neighbor
- Reduces build time
- Usually enabled

## Hatching Strategies

Currently available:
- **LINES**: Parallel line hatching ✅ Implemented

Coming soon (framework ready):
- ZIGZAG: Continuous back-and-forth
- GRID: Crossed perpendicular lines
- HONEYCOMB: Hexagonal cells
- CONCENTRIC: Spiral from outside in
- HILBERT: Space-filling curve
- SPIRAL: Continuous spiral
- ADAPTIVE: Variable density

## Troubleshooting

### Problem: "No Model" error when generating
**Solution**: Load a CAD file first (File → Open)

### Problem: "Not in Slice Mode" error
**Solution**: Click "Slice Mode" button before generating

### Problem: No hatching visible
**Solution**:
1. Check hatching was generated (Tools → Hatching Parameters, see statistics)
2. Navigate to correct layer using scrollbar
3. Verify hatching enabled in dialog

### Problem: Slow generation
**Solution**:
- Increase hatch spacing (0.2 mm instead of 0.1 mm)
- Disable path optimization
- Simplify CAD geometry

### Problem: Export fails
**Solution**:
- Generate hatching first
- Check write permissions for output directory
- Try different file format (.json instead of .obp)

## Tips & Tricks

### Optimize Build Time
1. Use bidirectional scanning
2. Enable path optimization
3. Increase hatch spacing (if material allows)
4. Reduce contour count

### Improve Part Quality
1. Decrease hatch spacing
2. Add multiple contours (2-3)
3. Use layer rotation (67°)
4. Adjust power/speed for material

### Large Models
- Slice mode may take time for large files
- Hatching generation scales with layer count
- Use larger layer thickness for preview
- Refine settings before final generation

### Preview Before Export
1. Generate with default parameters
2. Check statistics (total time, line count)
3. Navigate layers to verify coverage
4. Adjust parameters if needed
5. Regenerate and verify
6. Export when satisfied

## Statistics Interpretation

**Total Layers**: Number of slices
**Total Lines**: Sum of all scan vectors
**Contour Lines**: Perimeter scans
**Infill Lines**: Interior fill scans
**Scan Length**: Total distance traveled
**Estimated Time**: Build time estimate (excluding layer changes, recoating)
**Avg Lines/Layer**: Average complexity per layer

## Example Workflows

### Simple Preview
```
1. Open model
2. Slice mode
3. Use default parameters
4. Generate
5. Review
```

### Production Build
```
1. Open model
2. Slice mode (set correct layer thickness)
3. Configure parameters for material
4. Generate
5. Review statistics
6. Verify critical layers
7. Export to OBP
8. Send to machine
```

### Parameter Tuning
```
1. Start with defaults
2. Generate and note build time
3. Adjust one parameter
4. Regenerate
5. Compare statistics
6. Iterate until optimal
```

## Support

- Documentation: See `hatching/README.md`
- Integration details: See `INTEGRATION_COMPLETE.md`
- Examples: Run `python hatching/example.py`
- Tests: Run `python -m hatching.test_plugin_system`

## Next Steps

After mastering basics:
1. Implement custom hatching strategies (see `hatching/README.md`)
2. Integrate obplib for native OBP export
3. Develop additional strategies (zigzag, grid, etc.)
4. Optimize parameters for your specific material/process

---

**Quick Help**: Press Ctrl+H to open Hatching Parameters dialog
