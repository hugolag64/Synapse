from nicegui import ui

class SortableList(ui.element):
    def __init__(self, on_change=None):
        super().__init__('div')
        self.classes('sortable-list')
        self._on_change = on_change
        
        # Hidden button to proxy the event to Python
        # We put it first. It will be ignored by Sortable via 'draggable' selector
        with self:
            self._trigger = ui.button().props('round').style('display:none')
            self._trigger.on('click', self._handle_click_event)
        
        ui.add_head_html('<script src="https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js"></script>')
        ui.timer(0.1, self.init_sortable, once=True)

    def _handle_click_event(self, e):
        """Handle the proxy click event with the new order."""
        try:
            if self._on_change:
                self._on_change(e.args)
        except Exception as ex:
            print(f"SortableList Error: {ex}")

    def init_sortable(self):
        # We target the button via its unique ID
        trigger_id = f"c{self._trigger.id}"
        
        init_script = f"""
            var domId = 'c{self.id}';
            var el = document.getElementById(domId);
            
            // Fallback finding
            if (!el) el = getElement({self.id})?.$el || getElement({self.id});
            if (!el) return console.error("SortableList: Element NOT found");

            // Look for the trigger component (Button)
            var triggerComponent = getElement({self._trigger.id}); 

            var checkSortable = setInterval(function() {{
                var lib = (typeof Sortable !== 'undefined') ? Sortable : window.Sortable;
                if (lib) {{
                    clearInterval(checkSortable);
                    new lib(el, {{
                        animation: 150,
                        ghostClass: 'bg-orange-100',
                        delay: 50, 
                        forceFallback: true,
                        draggable: ".cursor-move", // EXTREMELY IMPORTANT: Only drag items with this class
                        dataIdAttr: 'data-id', 
                        onEnd: function (evt) {{
                            // Get the new order of data-ids
                            var order = this.toArray();
                            
                            // Send to Python via the trigger button
                            if (triggerComponent) {{
                                triggerComponent.$emit('click', {{order: order}});
                            }}
                        }}
                    }});
                }}
            }}, 100);
        """
        ui.run_javascript(init_script)
