package com.suke.ai.mapper;

import com.suke.ai.pojo.Content;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * @author 自然醒
 * @version 1.0
 * @date 2026-02-09 14:45
 * @description 操作对话信息的映射接口
 */
@Mapper
public interface ContentMapper {
    @Select("select distinct conversation_id from content")
    List<String> findConversationIds();

    @Select("select * from content where conversation_id = #{conversationId} order by create_time")
    List<Content> findByConversationId(String conversationId);


    void insert(Content content);

    @Delete("delete from content where conversation_id = #{conversationId}")
    void deleteByConversationId(String conversationId);
}
