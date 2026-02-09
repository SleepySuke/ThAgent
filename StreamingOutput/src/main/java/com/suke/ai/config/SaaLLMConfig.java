package com.suke.ai.config;

import com.alibaba.cloud.ai.dashscope.api.DashScopeApi;
import com.alibaba.cloud.ai.dashscope.chat.DashScopeChatModel;
import com.alibaba.cloud.ai.dashscope.chat.DashScopeChatOptions;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * @author 自然醒
 * @version 1.0
 */

//ChatModel与ChatClient结合使用实现流式输出sse及多模型共存
@Configuration
public class SaaLLMConfig {
    @Value("${spring.ai.dashscope.api-key}")
    private String apiKey;
    private static final String DEEPSEEK_MODEL = "deepseek-v3";
    private static final String QWEN_MODEL = "qwen-plus";

    @Bean(name = "deepseek")
//    @ConditionalOnMissingBean
//    注意如果是同类型的bean不要使用该注解，不然会导致出错，无法再注册同一个类型的bean
//    如果是多个不同类型的bean可以使用该注解
    public ChatModel deepseekModel(){
        //使用DashScopeChatModel创建模型
        return DashScopeChatModel.builder()
                //配置DashScopeApi 构建DashScopeApi
                .dashScopeApi(DashScopeApi.builder().apiKey(apiKey).build())
                //配置模型名称
                .defaultOptions(DashScopeChatOptions.builder().withModel(DEEPSEEK_MODEL).build())
                .build();
    }
    @Bean(name = "qwen")
    public ChatModel qwenModel(){
        //使用DashScopeChatModel创建模型
        return DashScopeChatModel.builder()
                //配置DashScopeApi 构建DashScopeApi
                .dashScopeApi(DashScopeApi.builder().apiKey(apiKey).build())
                //配置模型名称
                .defaultOptions(DashScopeChatOptions.builder().withModel(QWEN_MODEL).build())
                .build();
    }

    @Bean(name = "deepseekChatClient")
    public ChatClient deepseekChatClient(@Qualifier("deepseek") ChatModel deepseekModel){
        return ChatClient.builder(deepseekModel).build();
    }
    @Bean(name = "qwenChatClient")
    public ChatClient qwenChatClient(@Qualifier("qwen") ChatModel qwenModel){
        return ChatClient.builder(qwenModel).build();
    }
}
