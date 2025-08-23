from typing import List, Dict, Any

class KnowledgeManager:
    def __init__(self):
        self.knowledge_base = {}

    def add_knowledge(self, knowledge, category, keywords):
        """添加知识到知识库
        
        Args:
            knowledge: 知识内容
            category: 知识分类
            keywords: 关键词列表
        """
        if category not in self.knowledge_base:
            self.knowledge_base[category] = []
        
        knowledge_item = {
            "knowledge": knowledge,
            "keywords": keywords,
            "category": category
        }
        self.knowledge_base[category].append(knowledge_item)

    def get_knowledge_by_category(self, category):
        """通过分类获取知识
        
        Args:
            category: 知识分类
            
        Returns:
            该分类下的所有知识列表
        """
        return self.knowledge_base.get(category, [])

    def get_knowledge_by_keywords(self, keywords):
        """通过关键词获取知识
        
        Args:
            keywords: 关键词列表
            
        Returns:
            包含任一关键词的所有知识列表
        """
        results = []
        for category, knowledge_list in self.knowledge_base.items():
            for knowledge_item in knowledge_list:
                # 检查知识项的关键词是否与搜索关键词有交集
                if any(keyword.lower() in [kw.lower() for kw in knowledge_item["keywords"]] 
                       for keyword in keywords):
                    results.append(knowledge_item)
        return results

    def search_knowledge(self, query):
        """搜索知识（支持分类和关键词混合搜索）
        
        Args:
            query: 搜索查询字符串
            
        Returns:
            匹配的知识列表
        """
        results = []
        query_lower = query.lower()
        
        for category, knowledge_list in self.knowledge_base.items():
            for knowledge_item in knowledge_list:
                # 检查分类是否匹配
                if query_lower in category.lower():
                    results.append(knowledge_item)
                    continue
                
                # 检查关键词是否匹配
                if any(query_lower in keyword.lower() for keyword in knowledge_item["keywords"]):
                    results.append(knowledge_item)
                    continue
                
                # 检查知识内容是否匹配
                if query_lower in knowledge_item["knowledge"].lower():
                    results.append(knowledge_item)
        
        return results

    def get_all_categories(self):
        """获取所有知识分类
        
        Returns:
            分类列表
        """
        return list(self.knowledge_base.keys())

    def get_knowledge_count(self):
        """获取知识总数
        
        Returns:
            知识总数
        """
        total = 0
        for category, knowledge_list in self.knowledge_base.items():
            total += len(knowledge_list)
        return total

    def get_knowledge(self):
        """获取所有知识（保持向后兼容）"""
        return self.knowledge_base

    def remove_knowledge(self, category, knowledge_index=None):
        """删除知识
        
        Args:
            category: 知识分类
            knowledge_index: 知识索引，如果为None则删除整个分类
        """
        if category in self.knowledge_base:
            if knowledge_index is None:
                del self.knowledge_base[category]
            elif 0 <= knowledge_index < len(self.knowledge_base[category]):
                self.knowledge_base[category].pop(knowledge_index)

knowledge_manager = KnowledgeManager()
