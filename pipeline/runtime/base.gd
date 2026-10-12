extends SceneTree
var args = {}
var checks = []
var world
var expected = []
var last_mouse = Vector2.ZERO
func _initialize():
 for arg in OS.get_cmdline_user_args():
  var pair = arg.split("=", true, 1)
  if pair.size() == 2: args[pair[0]] = pair[1]
 root.size = Vector2i(ProjectSettings.get_setting("display/window/size/viewport_width",1152), ProjectSettings.get_setting("display/window/size/viewport_height",648))
 root.physics_object_picking = true
 call_deferred("run")
func run():
 expected = baseline_ids() if args.get("--mode") == "baseline" else full_ids()
 seed(20261006)
 await fresh()
 if args.get("--mode") == "baseline": await baseline()
 else: await evaluate()
 await finish()
func fresh():
 root.size = Vector2i(ProjectSettings.get_setting("display/window/size/viewport_width",1152), ProjectSettings.get_setting("display/window/size/viewport_height",648))
 if is_instance_valid(world):
  world.queue_free()
  await frames(4)
 world = load(ProjectSettings.get_setting("application/run/main_scene")).instantiate()
 root.add_child(world)
 current_scene = world
 await frames(8)
func frames(n):
 for i in n:
  await physics_frame
  if is_instance_valid(current_scene): world = current_scene
func check(id, condition, detail):
 checks.append({"check_id":id,"status":"PASS" if condition else "FAIL","observed":str(detail)})
 return bool(condition)
func key(code,down):
 var e = InputEventKey.new()
 e.keycode=code; e.physical_keycode=code; e.pressed=down
 Input.parse_input_event(e)
func tap(code,n=4):
 key(code,true);await frames(2);key(code,false);await frames(n)
func move_mouse(pos,buttons=0):
 var e=InputEventMouseMotion.new();e.position=root.get_final_transform()*pos;e.global_position=e.position;e.button_mask=buttons;e.relative=e.position-last_mouse;last_mouse=e.position
 Input.parse_input_event(e)
 await frames(2)
func mouse(pos,down,button=MOUSE_BUTTON_LEFT):
 var e=InputEventMouseButton.new();e.position=root.get_final_transform()*pos;e.global_position=e.position;e.pressed=down;e.button_mask=MOUSE_BUTTON_MASK_LEFT if down else 0;e.button_index=button
 Input.parse_input_event(e)
 await frames(2)
func click_at(pos):
 await move_mouse(pos);await mouse(pos,true);await mouse(pos,false);await frames(3)
func click(node):
 if not is_instance_valid(node):return false
 var pos = node.get_global_transform_with_canvas() * (node.size/2)
 await click_at(pos)
 return true
func drag(from,to):
 await move_mouse(from);await mouse(from,true)
 for i in range(1,7):await move_mouse(from.lerp(to,i/6.0),MOUSE_BUTTON_MASK_LEFT)
 await mouse(to,false);await frames(8)
func capture(label):
 if DisplayServer.get_name() == "headless":return
 await frames(3);await RenderingServer.frame_post_draw
 root.get_texture().get_image().save_png(args["--capture"]+"/"+label+".png")
func button(action):
 for n in get_nodes_in_group("task_controls"):
  if n is BaseButton and n.get_meta("action","")==action:return n
 return null
func state():
 var ns=get_nodes_in_group("task_state")
 if ns.size()==1 and ns[0].has_method("snapshot"):return ns[0].snapshot()
 return {}
func has_feature():
 var ns=get_nodes_in_group("task_state")
 return ns.size()==1 and ns[0].has_method("snapshot")
func baseline_ids():return ["base"]
func full_ids():return ["feature"]
func baseline():check("base",is_instance_valid(world),"main scene ready")
func evaluate():check("feature",has_feature(),"public observer")
func finish():
 var ids=checks.map(func(c):return c.check_id)
 for id in expected:
  if not id in ids:checks.append({"check_id":id,"status":"NOT_RUN","observed":"Prerequisite failed; no implied success"})
 for n in root.find_children("*","AudioStreamPlayer",true,false)+root.find_children("*","AudioStreamPlayer2D",true,false):n.stop();n.stream=null
 OS.delay_msec(250) # Let the audio mixer release stopped playback at real wall-clock speed.
 if is_instance_valid(world):world.queue_free()
 await frames(60)
 var f=FileAccess.open(args["--report"],FileAccess.WRITE)
 f.store_string(JSON.stringify({"complete":true,"nonce":args["--nonce"],"checks":checks},"  "));f.close()
 quit(0 if checks.all(func(c):return c.status=="PASS") else 1)

func numbers(text):
 var regex=RegEx.new();regex.compile("[0-9]+(?:\\.[0-9]+)?")
 return regex.search_all(text).map(func(m):return float(m.get_string()))
func has_number(text,value,tolerance=0.01):
 return numbers(text).any(func(v):return abs(v-value)<=tolerance)
func hud(field):
 for n in get_nodes_in_group("task_hud"):
  if n.get_meta("field","")==field:return n
 return null
