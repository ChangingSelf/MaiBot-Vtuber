class ToDoItem:
    def __init__(self, type: str, details: str, done_criteria: str, progress: str):
        self.type:str = type
        self.details:str = details
        self.done_criteria:str = done_criteria
        self.progress:str = progress
        self.done:bool = False

        self.id:str = ""
        
    def __str__(self):
        return f"类型：{self.type}，详情：{self.details}，progress：{self.progress}，完成条件：{self.done_criteria}，是否完成：{self.done}"

class ToDoList:
    def __init__(self):
        self.items:list[ToDoItem] = []
        
        self.is_done:bool = False
        self.need_edit:str = ""
        
    def add_task(self, type: str, details: str, done_criteria: str):
        to_do_item = ToDoItem(type, details, done_criteria, "尚未开始")
        to_do_item.id = str(len(self.items)+1)
        self.items.append(to_do_item)
        
    def __str__(self):
        summary = ""
        for item in self.items:
            summary += f"任务(id:{item.id})，类型：{item.type}，详情：{item.details}\n目前进度：{item.progress}\n完成条件：{item.done_criteria}\n是否完成：{item.done}\n"
        return summary

    
    def clear(self):
        self.items.clear()
        self.is_done = False
                
    def get_task_by_id(self, id: str):
        for item in self.items:
            if item.id == id:
                return item
        return None

    
    def check_if_all_done(self):
        for item in self.items:
            if not item.done:
                return False
            
        self.is_done = True
        return True
        
        