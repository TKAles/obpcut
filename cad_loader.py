"""
CAD file loader for STEP and IGES files using OCP (OpenCascade).
Extracts BREP data for OpenGL rendering with minimal tessellation.
"""

from OCP.STEPControl import STEPControl_Reader
from OCP.IGESControl import IGESControl_Reader
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Edge
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.Poly import Poly_Triangulation, Poly_PolygonOnTriangulation
from OCP.TColgp import TColgp_Array1OfPnt
from OCP.gp import gp_Pnt
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
import numpy as np
from typing import Optional, List, Tuple, Callable
import traceback

# Constants for tessellation quality
LINEAR_DEFLECTION = 0.1  # mm - very fine tessellation
ANGULAR_DEFLECTION = 0.1  # radians - smooth curves
UNIT_SCALE = 1.0  # Scale factor for unit conversion


class CADModel:
    """Represents a loaded CAD model with BREP data for rendering"""

    def __init__(self):
        self.vertices = []  # List of vertex positions [x, y, z]
        self.normals = []   # List of vertex normals [nx, ny, nz]
        self.indices = []   # List of triangle indices for faces

        # Edge data for BREP-style rendering
        self.edge_vertices = []  # List of edge line segments
        self.edge_indices = []   # Indices for edge lines

        self.bounds = None  # Bounding box (min_x, min_y, min_z, max_x, max_y, max_z)

    def get_center(self):
        """Get the center point of the model"""
        if self.bounds:
            min_x, min_y, min_z, max_x, max_y, max_z = self.bounds
            return [(min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2]
        return [0, 0, 0]

    def get_scale_factor(self, target_size=2.0):
        """Get scale factor to fit model in a target size"""
        if self.bounds:
            min_x, min_y, min_z, max_x, max_y, max_z = self.bounds
            size_x = max_x - min_x
            size_y = max_y - min_y
            size_z = max_z - min_z
            max_size = max(size_x, size_y, size_z)
            if max_size > 0:
                return target_size / max_size
        return 1.0


def load_cad_file(file_path: str) -> Optional[CADModel]:
    """
    Load a CAD file (STEP or IGES) and extract BREP data with minimal tessellation.

    Args:
        file_path: Path to the STEP or IGES file

    Returns:
        CADModel object with BREP data, or None if loading failed
    """
    return load_cad_file_with_progress(file_path, None)


def load_cad_file_with_progress(
    file_path: str,
    progress_callback: Optional[Callable[[str, str], None]] = None
) -> Optional[CADModel]:
    """
    Load a CAD file with progress reporting (thread-safe).

    Args:
        file_path: Path to the STEP or IGES file
        progress_callback: Optional callback(stage, message) for progress updates

    Returns:
        CADModel object with BREP data, or None if loading failed
    """
    def report_progress(stage: str, message: str):
        """Helper to report progress if callback is provided."""
        if progress_callback:
            progress_callback(stage, message)

    try:
        report_progress("loading", f"Loading CAD file: {file_path}")

        # Determine file type and load
        file_path_lower = file_path.lower()
        shape = None

        if file_path_lower.endswith('.step') or file_path_lower.endswith('.stp'):
            # Load STEP file
            report_progress("reading", "Reading STEP file...")
            reader = STEPControl_Reader()
            status = reader.ReadFile(file_path)

            if status != IFSelect_ReturnStatus.IFSelect_RetDone:
                raise ValueError("Error reading STEP file")

            report_progress("transferring", "Transferring STEP data...")
            reader.TransferRoots()
            shape = reader.OneShape()

        elif file_path_lower.endswith('.iges') or file_path_lower.endswith('.igs'):
            # Load IGES file
            report_progress("reading", "Reading IGES file...")
            reader = IGESControl_Reader()
            status = reader.ReadFile(file_path)

            if status != IFSelect_ReturnStatus.IFSelect_RetDone:
                raise ValueError("Error reading IGES file")

            report_progress("transferring", "Transferring IGES data...")
            reader.TransferRoots()
            shape = reader.OneShape()
        else:
            raise ValueError(f"Unsupported file format: {file_path}")

        if not shape:
            raise ValueError("Failed to load shape from file")

        report_progress("tessellating", "Tessellating geometry...")

        # Tessellate the shape with high quality settings for BREP appearance
        mesh = BRepMesh_IncrementalMesh(
            shape, LINEAR_DEFLECTION, False, ANGULAR_DEFLECTION, True
        )
        mesh.Perform()

        if not mesh.IsDone():
            raise RuntimeError("Tessellation failed")

        report_progress("extracting", "Extracting geometry...")

        # Create CADModel to store the data
        model = CADModel()

        # Calculate bounding box
        bbox = Bnd_Box()
        BRepBndLib.Add_s(shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

        model.bounds = (xmin, ymin, zmin, xmax, ymax, zmax)

        # Extract faces (surfaces)
        report_progress("extracting", "Extracting faces...")
        face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
        vertex_offset = 0

        while face_explorer.More():
            face = TopoDS.Face_s(face_explorer.Current())
            location = TopLoc_Location()
            triangulation = BRep_Tool.Triangulation_s(face, location)

            if triangulation:
                # Get transformation
                transform = location.Transformation()

                # Extract vertices
                num_nodes = triangulation.NbNodes()

                face_vertices = []
                for i in range(1, num_nodes + 1):
                    pnt = triangulation.Node(i)
                    # Apply transformation
                    pnt.Transform(transform)
                    # Apply unit scaling
                    face_vertices.append([
                        pnt.X() * UNIT_SCALE,
                        pnt.Y() * UNIT_SCALE,
                        pnt.Z() * UNIT_SCALE
                    ])

                # Extract triangles
                num_triangles = triangulation.NbTriangles()

                for i in range(1, num_triangles + 1):
                    tri = triangulation.Triangle(i)
                    n1, n2, n3 = tri.Get()

                    # Adjust for 1-based indexing and add vertex offset
                    model.indices.extend([
                        vertex_offset + n1 - 1,
                        vertex_offset + n2 - 1,
                        vertex_offset + n3 - 1
                    ])

                # Add vertices to model
                model.vertices.extend(face_vertices)
                vertex_offset = len(model.vertices)

            face_explorer.Next()

        # Extract edges for BREP-style outline rendering
        report_progress("extracting", "Extracting edges...")
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GCPnts import GCPnts_UniformDeflection

        edge_explorer = TopExp_Explorer(shape, TopAbs_EDGE)
        edge_vertex_offset = 0

        while edge_explorer.More():
            edge = TopoDS.Edge_s(edge_explorer.Current())

            # Get the curve from the edge
            try:
                curve_adaptor = BRepAdaptor_Curve(edge)

                # Discretize the curve with the same deflection as the mesh
                discretizer = GCPnts_UniformDeflection(curve_adaptor, LINEAR_DEFLECTION)

                if discretizer.IsDone() and discretizer.NbPoints() > 1:
                    num_points = discretizer.NbPoints()

                    # Extract points along the edge
                    for i in range(1, num_points + 1):
                        pnt = discretizer.Value(i)
                        model.edge_vertices.append([
                            pnt.X() * UNIT_SCALE,
                            pnt.Y() * UNIT_SCALE,
                            pnt.Z() * UNIT_SCALE
                        ])

                    # Create line segments
                    for i in range(num_points - 1):
                        model.edge_indices.extend([
                            edge_vertex_offset + i,
                            edge_vertex_offset + i + 1
                        ])

                    edge_vertex_offset = len(model.edge_vertices)
            except Exception as e:
                # Skip edges that fail (degenerate edges, etc.)
                # This is expected for some edge cases in CAD models
                pass

            edge_explorer.Next()

        # Calculate vertex normals
        report_progress("computing", "Computing normals...")
        vertex_normals = [[0.0, 0.0, 0.0] for _ in range(len(model.vertices))]

        # Calculate face normals and accumulate to vertices
        for i in range(0, len(model.indices), 3):
            i0, i1, i2 = model.indices[i], model.indices[i+1], model.indices[i+2]

            # Get triangle vertices
            v0 = np.array(model.vertices[i0])
            v1 = np.array(model.vertices[i1])
            v2 = np.array(model.vertices[i2])

            # Calculate face normal
            edge1 = v1 - v0
            edge2 = v2 - v0
            normal = np.cross(edge1, edge2)

            # Normalize
            length = np.linalg.norm(normal)
            if length > 0:
                normal = normal / length

            # Accumulate to vertex normals
            for idx in [i0, i1, i2]:
                vertex_normals[idx][0] += normal[0]
                vertex_normals[idx][1] += normal[1]
                vertex_normals[idx][2] += normal[2]

        # Normalize all vertex normals
        for i in range(len(vertex_normals)):
            normal = np.array(vertex_normals[i])
            length = np.linalg.norm(normal)
            if length > 0:
                normal = normal / length
                vertex_normals[i] = normal.tolist()

        model.normals = vertex_normals

        min_x, min_y, min_z, max_x, max_y, max_z = model.bounds

        report_progress("complete", "Loading complete!")
        print(f"Geometry extracted: {len(model.vertices)} vertices, "
              f"{len(model.indices)//3} triangles, {len(model.edge_indices)//2} edge segments")
        print(f"Bounds (mm): ({min_x:.2f}, {min_y:.2f}, {min_z:.2f}) to "
              f"({max_x:.2f}, {max_y:.2f}, {max_z:.2f})")
        print(f"Model size: {max_x - min_x:.2f} x {max_y - min_y:.2f} x "
              f"{max_z - min_z:.2f} mm")

        return model

    except Exception as e:
        error_msg = f"Error loading CAD file: {e}"
        print(error_msg)
        traceback.print_exc()
        report_progress("error", error_msg)
        raise
