import numpy as np
import vtk
import gmsh
import math
import os


# Класс расчётной сетки
class CalcMesh:

    # Конструктор сетки, полученной из stl-файла
    def __init__(self, nodes_coords, tetrs_points):
        # 3D-сетка из расчётных точек
        # Пройдём по узлам в модели gmsh и заберём из них координаты
        self.nodes = np.array([nodes_coords[0::3], nodes_coords[1::3], nodes_coords[2::3]])

        # Модельная скалярная величина распределена как-то вот так
        min_coord_0 = np.ones(len(nodes_coords) // 3) * (np.min(self.nodes[0, :]) + 0.31)
        min_coord_1 = np.ones(len(nodes_coords) // 3) * np.max(self.nodes[1, :])
        min_coord_2 = np.ones(len(nodes_coords) // 3) * (np.min(self.nodes[2, :]) + 0.44)

        self.smth = np.power((np.power(self.nodes[0, :] - min_coord_0, 2) + np.power(self.nodes[1, :] - min_coord_1, 2) \
                              + np.power(self.nodes[2, :] - min_coord_2, 2)), 0.5) * 1750

        # Тут может быть скорость, но сейчас здесь нули
        max_y = np.max(self.nodes[1, :])
        min_y = np.min(self.nodes[1, :])
        delta = np.abs(self.nodes[1] - np.ones(len(nodes_coords) // 3) * np.min(self.nodes[1]))
        self.velocity = np.zeros(shape=(3, len(nodes_coords) // 3), dtype=np.double)

        max_delta = 0
        for i in range(len(nodes_coords) // 3):
            if nodes_coords[i * 3 + 1] < -0.46875:
                max_delta = max(max_delta, delta[i])

        for i in range(len(nodes_coords) // 3):
            if nodes_coords[i * 3 + 1] < -0.46875:
                self.velocity[2][i] = (max_delta - delta[i]) * (-0.5)


        # Пройдём по элементам в модели gmsh
        self.tetrs = np.array([tetrs_points[0::4], tetrs_points[1::4], tetrs_points[2::4], tetrs_points[3::4]])
        self.tetrs -= 1

    # Метод отвечает за выполнение для всей сетки шага по времени величиной tau
    def move(self, tau):
        # По сути метод просто двигает все точки c их текущими скоростями
        self.nodes += self.velocity * tau

    # Метод отвечает за запись текущего состояния сетки в снапшот в формате VTK
    def snapshot(self, snap_number):
        # Сетка в терминах VTK
        unstructuredGrid = vtk.vtkUnstructuredGrid()
        # Точки сетки в терминах VTK
        points = vtk.vtkPoints()

        # Скалярное поле на точках сетки
        smth = vtk.vtkDoubleArray()
        smth.SetName("smth")

        # Векторное поле на точках сетки
        vel = vtk.vtkDoubleArray()
        vel.SetNumberOfComponents(3)
        vel.SetName("vel")

        # Обходим все точки нашей расчётной сетки
        # Делаем это максимально неэффективным, зато наглядным образом
        for i in range(0, len(self.nodes[0])):
            # Вставляем новую точку в сетку VTK-снапшота
            points.InsertNextPoint(self.nodes[0, i], self.nodes[1, i], self.nodes[2, i])
            # Добавляем значение скалярного поля в этой точке
            smth.InsertNextValue(self.smth[i])
            # Добавляем значение векторного поля в этой точке
            vel.InsertNextTuple((self.velocity[0, i], self.velocity[1, i], self.velocity[2, i]))

        # Грузим точки в сетку
        unstructuredGrid.SetPoints(points)

        # Присоединяем векторное и скалярное поля к точкам
        unstructuredGrid.GetPointData().AddArray(smth)
        unstructuredGrid.GetPointData().AddArray(vel)

        # А теперь пишем, как наши точки объединены в тетраэдры
        # Делаем это максимально неэффективным, зато наглядным образом
        for i in range(0, len(self.tetrs[0])):
            tetr = vtk.vtkTetra()
            for j in range(0, 4):
                tetr.GetPointIds().SetId(j, self.tetrs[j, i])
            unstructuredGrid.InsertNextCell(tetr.GetCellType(), tetr.GetPointIds())

        # Создаём снапшот в файле с заданным именем
        writer = vtk.vtkXMLUnstructuredGridWriter()
        writer.SetInputDataObject(unstructuredGrid)
        writer.SetFileName("pig-step-" + str(snap_number) + ".vtu")
        writer.Write()


# Теперь придётся немного упороться:
# (а) построением сетки средствами gmsh,
# (б) извлечением данных этой сетки в свой код.
gmsh.initialize()

# Считаем STL
try:
    path = os.path.dirname(os.path.abspath(__file__))
    gmsh.merge(os.path.join(path, 'pig.stl'))
except:
    print("Could not load STL mesh: bye!")
    gmsh.finalize()
    exit(-1)

# Восстановим геометрию
angle = 40
forceParametrizablePatches = True
includeBoundary = True
curveAngle = 100
gmsh.model.mesh.classifySurfaces(angle * math.pi / 180., includeBoundary, forceParametrizablePatches,
                                 curveAngle * math.pi / 180.)
gmsh.model.mesh.createGeometry()

# Зададим объём по считанной поверхности
s = gmsh.model.getEntities(2)
l = gmsh.model.geo.addSurfaceLoop([s[i][1] for i in range(len(s))])
gmsh.model.geo.addVolume([l])

gmsh.model.geo.synchronize()

# Зададим мелкость желаемой сетки
f = gmsh.model.mesh.field.add("MathEval")
gmsh.model.mesh.field.setString(f, "F", "0.05")
gmsh.model.mesh.field.setAsBackgroundMesh(f)

# Построим сетку
gmsh.model.mesh.generate(3)

# Теперь извлечём из gmsh данные об узлах сетки
nodeTags, nodesCoord, parametricCoord = gmsh.model.mesh.getNodes()

# И данные об элементах сетки тоже извлечём, нам среди них нужны только тетраэдры, которыми залит объём
GMSH_TETR_CODE = 4
tetrsNodesTags = None
elementTypes, elementTags, elementNodeTags = gmsh.model.mesh.getElements()
for i in range(0, len(elementTypes)):
    if elementTypes[i] != GMSH_TETR_CODE:
        continue
    tetrsNodesTags = elementNodeTags[i]

if tetrsNodesTags is None:
    print("Can not find tetra data. Exiting.")
    gmsh.finalize()
    exit(-2)

print("The model has %d nodes and %d tetrs" % (len(nodeTags), len(tetrsNodesTags) / 4))

# На всякий случай проверим, что номера узлов идут подряд и без пробелов
for i in range(0, len(nodeTags)):
    # Индексация в gmsh начинается с 1, а не с нуля. Ну штош, значит так.
    assert (i == nodeTags[i] - 1)
# И ещё проверим, что в тетраэдрах что-то похожее на правду лежит.
assert (len(tetrsNodesTags) % 4 == 0)

# TODO: неплохо бы полноценно данные сетки проверять, да

mesh = CalcMesh(nodesCoord, tetrsNodesTags)
mesh.snapshot(0)

# Делаем шаги по времени,
# на каждом шаге считаем новое состояние и пишем его в VTK
# Шаг точек по пространству
h = 0.1
# Шаг по времени
tau = 0.01
for i in range(1, 100):
    mesh.move(tau)
    mesh.snapshot(i)
gmsh.finalize()
