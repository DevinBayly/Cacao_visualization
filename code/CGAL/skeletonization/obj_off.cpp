#include <CGAL/Surface_mesh.h>
#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
// #include <CGAL/Polygon_mesh_processing/IO/polygon_mesh_io.h>
#include <CGAL/IO/polygon_mesh_io.h>
#include <iostream>
#include <fstream>
#include <string>

// Define the kernel and the mesh type
typedef CGAL::Exact_predicates_inexact_constructions_kernel K;
typedef CGAL::Surface_mesh<K::Point_3> Mesh;

namespace PMP = CGAL::Polygon_mesh_processing;

int main(int argc, char* argv[]) {
    // Check command line arguments
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <input.obj> <output.off>" << std::endl;
        return 1;
    }

    const std::string input_filename = argv[1];
    const std::string output_filename = argv[2];
    Mesh mesh;

    // 1. Read the OBJ file into the Surface_mesh
    std::cout << "Reading " << input_filename << "..." << std::endl;
    // PMP::IO::read_polygon_mesh handles various formats, including OBJ,
    // and is generally recommended over the stream operators for files.
    if (!CGAL::IO::read_polygon_mesh(input_filename, mesh)) {
        std::cerr << "ERROR: Failed to read polygon mesh from " << input_filename << std::endl;
        return 1;
    }

    if (mesh.is_empty()) {
        std::cerr << "ERROR: The mesh is empty after reading." << std::endl;
        return 1;
    }

    std::cout << "Mesh read successfully. Vertices: " << mesh.number_of_vertices()
              << ", Faces: " << mesh.number_of_faces() << std::endl;

    // 2. Write the Surface_mesh to the OFF file
    std::cout << "Writing to " << output_filename << "..." << std::endl;
    std::ofstream os(output_filename);
    
    // PMP::IO::write_polygon_mesh handles various formats, including OFF
    if (!CGAL::IO::write_polygon_mesh(output_filename, mesh, CGAL::parameters::stream_precision(10))) {
        std::cerr << "ERROR: Failed to write polygon mesh to " << output_filename << std::endl;
        return 1;
    }

    std::cout << "Conversion complete: " << input_filename << " -> " << output_filename << std::endl;

    return 0;
}