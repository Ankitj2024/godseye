
    let scene, camera, renderer, controls, droneControls;
    let meshGroup, cuboidGroup, gridHelper, pointcloudGroup, depthGroup;
    let sceneMaxDim = 10;
    
    // Drone Mode State
    let isDroneMode = false;
    const keys = { w: false, a: false, s: false, d: false };
    const droneVelocity = new THREE.Vector3();
    const clock = new THREE.Clock();

    const layers = { mesh: true, wireframe: false, cuboids: true, grid: true, pointcloud: false, depthcloud: false };
    const classColors = { vehicle: 0x525252, building: 0x525252, tree: 0x525252, road: 0x525252, person: 0x525252, default: 0x525252 };

    // Setup ThreeJS
    function initThree() {
      const container = document.getElementById('viewport');
      scene = new THREE.Scene();
      scene.background = new THREE.Color(0xffffff); // canvas white
      scene.fog = new THREE.FogExp2(0xffffff, 0.005);

      camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 2000);
      camera.position.set(0, -40, 30);
      camera.up.set(0, 0, 1);

      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(window.devicePixelRatio);
      renderer.setSize(window.innerWidth, window.innerHeight);
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.0;
      container.appendChild(renderer.domElement);

      controls = new THREE.TrackballControls(camera, renderer.domElement);
      controls.rotateSpeed = 4.0;
      controls.zoomSpeed = 1.2;
      controls.panSpeed = 0.8;

      // Init Drone Controls
      droneControls = new THREE.PointerLockControls(camera, renderer.domElement);
      droneControls.addEventListener('lock', () => {
        isDroneMode = true;
        controls.enabled = false;
        document.getElementById('btn-drone').textContent = "Exit Drone Mode (ESC)";
        document.getElementById('crosshair').style.display = 'block';
      });
      droneControls.addEventListener('unlock', () => {
        isDroneMode = false;
        controls.enabled = true;
        // Step forward slightly to look at where we stopped
        const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
        controls.target.copy(camera.position).add(forward.multiplyScalar(sceneMaxDim * 0.5));
        document.getElementById('btn-drone').textContent = "Enter Drone Mode";
        document.getElementById('crosshair').style.display = 'none';
      });
      scene.add(droneControls.getObject());

      scene.add(new THREE.AmbientLight(0xffffff, 0.6));
      const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.0);
      dirLight1.position.set(50, -50, 100);
      scene.add(dirLight1);

      // Soft gray grid
      gridHelper = new THREE.GridHelper(100, 50, 0xe5e5e5, 0xfafafa);
      gridHelper.rotation.x = Math.PI / 2;
      scene.add(gridHelper);

      meshGroup = new THREE.Group();
      cuboidGroup = new THREE.Group();
      pointcloudGroup = new THREE.Group();
      depthGroup = new THREE.Group();

      pointcloudGroup.visible = false;
      depthGroup.visible = false;

      scene.add(meshGroup);
      scene.add(cuboidGroup);
      scene.add(pointcloudGroup);
      scene.add(depthGroup);

      window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
      });

      setupRaycaster();
      setupDroneKeys();
      animate();
    }

    function setupDroneKeys() {
      window.addEventListener('keydown', (e) => {
        if (!isDroneMode) return;
        const key = e.key.toLowerCase();
        if (keys.hasOwnProperty(key)) keys[key] = true;
      });
      window.addEventListener('keyup', (e) => {
        if (!isDroneMode) return;
        const key = e.key.toLowerCase();
        if (keys.hasOwnProperty(key)) keys[key] = false;
      });
    }

    function toggleDroneMode() {
      if (isDroneMode) {
        droneControls.unlock();
      } else {
        droneControls.lock();
      }
    }

    function animate() {
      requestAnimationFrame(animate);
      const delta = clock.getDelta();

      if (isDroneMode) {
        // Friction
        droneVelocity.x -= droneVelocity.x * 10.0 * delta;
        droneVelocity.z -= droneVelocity.z * 10.0 * delta;

        const accel = sceneMaxDim * 6.0;

        if (keys.w) droneVelocity.z -= accel * delta;
        if (keys.s) droneVelocity.z += accel * delta;
        if (keys.a) droneVelocity.x -= accel * delta;
        if (keys.d) droneVelocity.x += accel * delta;

        // Move fully in 3D relative to the exact direction the camera is facing
        camera.translateX(-droneVelocity.x * delta);
        camera.translateZ(-droneVelocity.z * delta);
      } else {
        controls.update();
      }
      
      renderer.render(scene, camera);
    }

    function setupRaycaster() {
      const raycaster = new THREE.Raycaster();
      const mouse = new THREE.Vector2();
      const card = document.getElementById('object-card');

      window.addEventListener('pointermove', (event) => {
        if (isDroneMode) {
          mouse.x = 0;
          mouse.y = 0;
        } else {
          mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
          mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
        }
        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(cuboidGroup.children, true);
        const hit = intersects.find(i => i.object.userData && i.object.userData.obj);

        if (hit) {
          const data = hit.object.userData.obj;
          document.getElementById('card-class').textContent = data.object_class;
          document.getElementById('card-conf').textContent = `${Math.round(data.confidence * 100)}% Conf`;
          document.getElementById('card-id').textContent = data.object_id;
          document.getElementById('card-dims').textContent = `${data.dimensions.x.toFixed(1)} x ${data.dimensions.y.toFixed(1)} x ${data.dimensions.z.toFixed(1)}m`;
          const t = data.transform.translation;
          document.getElementById('card-pos').textContent = `(${t.x.toFixed(1)}, ${t.y.toFixed(1)}, ${t.z.toFixed(1)})`;
          document.getElementById('card-prov').textContent = data.provenance || 'OWLv2';
          card.style.display = 'block';
        } else {
          card.style.display = 'none';
        }
      });
    }

    function renderSemanticObjects(objects) {
      cuboidGroup.clear();
      objects.forEach((obj) => {
        const t = obj.transform.translation;
        const d = obj.dimensions;
        const color = classColors[obj.object_class] || classColors.default;

        const geom = new THREE.BoxGeometry(d.x, d.y, d.z);
        const wireframeGeom = new THREE.WireframeGeometry(geom);
        const line = new THREE.LineSegments(
          wireframeGeom,
          new THREE.LineBasicMaterial({ color: color, linewidth: 2, transparent: true, opacity: 0.5 })
        );

        const hitBox = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.05, depthWrite: false }));
        hitBox.userData = { obj: obj };

        const objContainer = new THREE.Group();
        objContainer.position.set(t.x, t.y, t.z);
        objContainer.add(line);
        objContainer.add(hitBox);
        cuboidGroup.add(objContainer);
      });

      buildObjectTree(objects);
    }

    function buildObjectTree(objects) {
      const container = document.getElementById('object-tree-container');
      const panel = document.getElementById('object-tree-panel');
      panel.style.display = 'flex';
      container.innerHTML = '';

      if (objects.length === 0) {
        container.innerHTML = '<div style="font-size: 13px; color: var(--colors-mute);">No objects found</div>';
        return;
      }

      const byClass = {};
      objects.forEach(obj => {
        if (!byClass[obj.object_class]) byClass[obj.object_class] = [];
        byClass[obj.object_class].push(obj);
      });

      Object.keys(byClass).sort().forEach(cls => {
        const folderWrapper = document.createElement('div');

        const folder = document.createElement('div');
        folder.className = 'tree-folder';
        folder.innerHTML = `<span style="font-size: 10px; width: 12px;">▼</span> <span>📁 ${cls}</span>`;

        const items = document.createElement('div');
        items.className = 'tree-items open';

        folder.onclick = () => {
          items.classList.toggle('open');
          folder.children[0].textContent = items.classList.contains('open') ? '▼' : '▶';
        };

        byClass[cls].forEach(obj => {
          const item = document.createElement('div');
          item.className = 'tree-item';

          item.innerHTML = `
            <span class="tree-icon">📄</span>
            <span>${obj.object_id}</span>
            <span style="color: var(--colors-mute); font-size: 11px;">${Math.round(obj.confidence * 100)}%</span>
          `;

          item.onclick = (e) => {
            e.stopPropagation();
            focusObject(obj);
          };
          items.appendChild(item);
        });

        folderWrapper.appendChild(folder);
        folderWrapper.appendChild(items);
        container.appendChild(folderWrapper);
      });
    }

    function focusObject(obj) {
      const t = obj.transform.translation;
      const target = new THREE.Vector3(t.x, t.y, t.z);

      controls.target.copy(target);
      // Position camera slightly above and pulled back from the object
      const maxD = Math.max(obj.dimensions.x, obj.dimensions.y, obj.dimensions.z);
      const dist = Math.max(maxD * 3, 10);
      camera.position.set(t.x, t.y - dist, t.z + dist * 0.8);
      controls.update();

      // Auto-show cuboids layer if it's hidden so they can see what they clicked
      if (!layers.cuboids) {
        toggleLayer('cuboids');
      }
    }

    function toggleLayer(layer) {
      layers[layer] = !layers[layer];
      const btn = document.getElementById(`toggle-${layer}`);
      if (btn) {
        if (layers[layer]) btn.classList.add('active');
        else btn.classList.remove('active');
      }

      if (layer === 'mesh') meshGroup.visible = layers.mesh;
      if (layer === 'cuboids') cuboidGroup.visible = layers.cuboids;
      if (layer === 'pointcloud') pointcloudGroup.visible = layers.pointcloud;
      if (layer === 'depthcloud') depthGroup.visible = layers.depthcloud;
      if (layer === 'grid') gridHelper.visible = layers.grid;
      if (layer === 'wireframe') {
        meshGroup.traverse((child) => {
          if (child.isMesh) child.material.wireframe = layers.wireframe;
        });
      }
    }

    function resetCamera() { controls.reset(); }

    function updateLoading(msg) {
      document.getElementById('loading-msg').textContent = msg;
    }

    // Local Directory Handling
    document.getElementById('folder-input').addEventListener('change', async (e) => {
      const files = Array.from(e.target.files);
      if (files.length === 0) return;

      document.getElementById('picker-overlay').style.display = 'none';
      document.getElementById('loading').style.display = 'flex';
      document.getElementById('main-panel').style.display = 'flex';
      document.getElementById('video-panel').style.display = 'flex';

      // Parse folder name for job ID display
      const folderName = files[0].webkitRelativePath.split('/')[0];
      document.getElementById('job-id-display').textContent = folderName;

      const getFile = (name) => files.find(f => f.name === name);

      const glbFile = getFile('exact_scene.glb');
      const objectsFile = getFile('objects.json');
      const sceneFile = getFile('scene.json');
      const rawPlyFile = getFile('pointcloud.ply');
      const depthPlyFile = getFile('depth_pointcloud.ply');

      // 1. Load Stats
      if (sceneFile) {
        const text = await sceneFile.text();
        try {
          const s = JSON.parse(text);
          if (s.geometry) {
            document.getElementById('stat-vertices').textContent = s.geometry.mesh_vertex_count ? s.geometry.mesh_vertex_count.toLocaleString() : '--';
            document.getElementById('stat-faces').textContent = s.geometry.mesh_triangle_count ? s.geometry.mesh_triangle_count.toLocaleString() : '--';
            document.getElementById('stat-cameras').textContent = s.geometry.registered_images || '--';
          }
        } catch (err) { console.error("Error parsing scene.json", err); }
      }

      // 2. Load Semantics
      if (objectsFile) {
        const text = await objectsFile.text();
        try {
          const objDoc = JSON.parse(text);
          if (objDoc.objects) {
            document.getElementById('stat-objects').textContent = objDoc.objects.length;
            renderSemanticObjects(objDoc.objects);
          }
        } catch (err) { console.error("Error parsing objects.json", err); }
      }

      // 3. Load 3D Geometry
      if (glbFile) {
        updateLoading('Loading exact_scene.glb...');
        const url = URL.createObjectURL(glbFile);
        const loader = new THREE.GLTFLoader();
        loader.load(url, (gltf) => {
          try {
            const model = gltf.scene;
            const box = new THREE.Box3().setFromObject(model);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());

            model.traverse((child) => {
              if (child.isMesh) {
                child.material.roughness = 0.6;
                child.material.metalness = 0.1;
              }
            });

            meshGroup.add(model);
            const maxDim = Math.max(size.x, size.y, size.z);
            sceneMaxDim = maxDim || 10;
            camera.position.set(center.x, center.y - sceneMaxDim * 1.5, center.z + sceneMaxDim * 0.8);
            controls.target.copy(center);
            controls.update();
          } catch(err) {
            console.error("Error loading GLTF geometry:", err);
          } finally {
            URL.revokeObjectURL(url);
            document.getElementById('loading').style.display = 'none';
          }
        });
      } else {
        document.getElementById('loading').style.display = 'none';
      }

      // 4. Load Raw Pointcloud (hidden by default)
      if (rawPlyFile) {
        const url = URL.createObjectURL(rawPlyFile);
        const loader = new THREE.PLYLoader();
        loader.load(url, (geom) => {
          const material = new THREE.PointsMaterial({ size: 0.1, vertexColors: true });
          const points = new THREE.Points(geom, material);
          pointcloudGroup.add(points);
          URL.revokeObjectURL(url);
        });
      }

      // 5. Load Depth Pointcloud (hidden by default)
      if (depthPlyFile) {
        const url = URL.createObjectURL(depthPlyFile);
        const loader = new THREE.PLYLoader();
        loader.load(url, (geom) => {
          const material = new THREE.PointsMaterial({ size: 0.15, vertexColors: true });
          const points = new THREE.Points(geom, material);
          depthGroup.add(points);
          URL.revokeObjectURL(url);
        });
      }
    });

    // Video Dropzone Handling
    const dropzone = document.getElementById('video-dropzone');
    const refVideo = document.getElementById('reference-video');

    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

    const handleVideoFile = (file) => {
      if (file && file.type.startsWith('video/')) {
        const url = URL.createObjectURL(file);
        refVideo.src = url;
        dropzone.style.display = 'none';
        refVideo.style.display = 'block';
        refVideo.play();
      }
    };

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      handleVideoFile(e.dataTransfer.files[0]);
    });

    dropzone.addEventListener('click', () => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'video/*';
      input.onchange = (e) => handleVideoFile(e.target.files[0]);
      input.click();
    });

    initThree();
  